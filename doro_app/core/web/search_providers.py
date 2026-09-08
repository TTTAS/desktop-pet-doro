"""搜尋來源提供者：把「找來源」從爬 Bing HTML 換成呼叫搜尋 API。"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass
from typing import Callable, Protocol

from ...utils.logger import get_logger

logger = get_logger(__name__)

MIN_SNIPPET_CHARS = 250
MIN_GOOD_SOURCES = 2
TARGET_SOURCES = 3
MAX_RESULTS = 6
SEARCH_TIMEOUT_S = 30
DEFAULT_SEARCH_DEPTH = "basic"
TAVILY_COUNTRY = "taiwan"


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    content: str | None = None
    score: float = 0.0

    @property
    def best_text(self) -> str:
        return (self.content or self.snippet or "").strip()


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list["SearchResult"]: ...


def search_backend_name(provider: object) -> str:
    """這次真正用到的引擎名（Fallback 會記 last_used）。"""
    used = getattr(provider, "last_used", None) or getattr(provider, "name", None)
    if used:
        return str(used)
    return provider.__class__.__name__


def _with_deadline(
    fn: Callable[[], list["SearchResult"]], timeout: int, what: str
) -> list["SearchResult"]:
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning(f"{what} 逾時 {timeout}s，放棄")
        return []
    except Exception as exc:
        logger.warning(f"{what} 出錯：{exc}")
        return []
    finally:
        ex.shutdown(wait=False)


class TavilyProvider:
    name = "Tavily"

    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = DEFAULT_SEARCH_DEPTH,
        country: str = TAVILY_COUNTRY,
        timeout: int = SEARCH_TIMEOUT_S,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._search_depth = (search_depth or DEFAULT_SEARCH_DEPTH).strip().lower()
        self._country = country
        self._timeout = int(timeout)
        self.last_used = ""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.last_used = ""
        if not self._api_key:
            return []
        out = _with_deadline(lambda: self._do_search(query, max_results), self._timeout, "Tavily")
        if out:
            self.last_used = self.name
        return out

    def _do_search(self, query: str, max_results: int) -> list[SearchResult]:
        from tavily import TavilyClient

        client = TavilyClient(api_key=self._api_key)
        kwargs = {
            "search_depth": self._search_depth,
            "max_results": int(max_results),
            "country": self._country,
        }
        try:
            resp = client.search(query, **kwargs)
        except TypeError:
            kwargs.pop("country", None)
            resp = client.search(query, **kwargs)
        results = resp.get("results", []) if isinstance(resp, dict) else []
        out: list[SearchResult] = []
        for r in results:
            url = str(r.get("url", "")).strip()
            if not url:
                continue
            content = str(r.get("content") or "")
            try:
                score = float(r.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            out.append(
                SearchResult(
                    url=url,
                    title=str(r.get("title", "")),
                    snippet=content,
                    content=content or None,
                    score=score,
                )
            )
        return out


class DdgsProvider:
    name = "DuckDuckGo"

    def __init__(self, *, timeout: int = SEARCH_TIMEOUT_S) -> None:
        self._timeout = int(timeout)
        self.last_used = ""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.last_used = ""
        out = _with_deadline(lambda: self._do_search(query, max_results), self._timeout, "ddgs")
        if out:
            self.last_used = self.name
        return out

    def _do_search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except Exception:
            from duckduckgo_search import DDGS

        out: list[SearchResult] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=int(max_results)):
                url = str(r.get("href") or r.get("url") or "").strip()
                if not url:
                    continue
                body = str(r.get("body") or "")
                out.append(SearchResult(url=url, title=str(r.get("title", "")), snippet=body))
        return out


class FallbackSearchProvider:
    name = "Fallback"

    def __init__(self, providers: list[SearchProvider]) -> None:
        self._providers = list(providers)
        self.last_used = ""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.last_used = ""
        for provider in self._providers:
            label = getattr(provider, "name", provider.__class__.__name__)
            try:
                results = provider.search(query, max_results)
            except Exception as exc:
                logger.warning(f"搜尋 {label} 出錯，換下一個：{exc}")
                results = []
            if results:
                self.last_used = getattr(provider, "last_used", None) or label
                logger.info(f"搜尋用 {self.last_used}，{len(results)} 筆")
                return results
            logger.info(f"搜尋 {label} 沒結果，換下一個")
        return []


def build_search_provider(
    tavily_key: str, *, search_depth: str = DEFAULT_SEARCH_DEPTH
) -> SearchProvider:
    key = (tavily_key or "").strip()
    if key:
        return FallbackSearchProvider(
            [TavilyProvider(key, search_depth=search_depth), DdgsProvider()]
        )
    return DdgsProvider()


_INJECTION_LINE_RE = re.compile(
    r"(忽略(以上|前面|先前).{0,6}(指示|指令|要求))"
    r"|(ignore\s+(all\s+)?previous)"
    r"|(system\s+prompt)"
    r"|(you\s+are\s+now)"
    r"|(disregard\s+the\s+above)",
    re.IGNORECASE,
)


def sanitize_source_text(text: str) -> str:
    if not text:
        return ""
    kept = [ln for ln in text.splitlines() if not _INJECTION_LINE_RE.search(ln)]
    return "\n".join(kept)
