"""搜尋來源提供者：把「找來源」從爬 Bing HTML 換成呼叫搜尋 API。

`VerifyPipeline` 只依賴 `SearchProvider` 這個介面。正式環境注入 Tavily（有 key）
或 ddgs（免 key）；測試注入假的。每個 provider 自己吞錯回空 list，
`FallbackSearchProvider` 依序試、回第一個非空結果——降級順序固定、永不 raise。

門（外面要用就從這裡進來）：
- ``build_search_provider(tavily_key, search_depth=...)`` … 依 key 組出 provider。
- ``sanitize_source_text(text)`` … 進 LLM 前剝掉可疑的注入行。
常數（見 docs/verify-stage1-checklist.md）：`MIN_SNIPPET_CHARS` 等。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ...utils.logger import get_logger

logger = get_logger(__name__)

# ── 釘死的常數 ────────────────────────────────────────────────
MIN_SNIPPET_CHARS = 250  # 每來源摘要 ≥ 此字數 → 視為「有料」（免補讀）
MIN_GOOD_SOURCES = 2  # 有料來源 ≥ 此值 → 完全不開瀏覽器
TARGET_SOURCES = 3  # 需補讀時，湊到幾個來源為止
MAX_RESULTS = 6  # 跟搜尋 API 要幾筆
SEARCH_TIMEOUT_S = 30  # 搜尋硬逾時（對齊 OpenClaw Tavily plugin）
DEFAULT_SEARCH_DEPTH = "basic"  # 可被設定覆寫成 "advanced"
TAVILY_COUNTRY = "taiwan"  # 只設 country；language/locale 不臆造


@dataclass
class SearchResult:
    """一筆搜尋結果。``content`` 是 API 抽好的內容（可能為 None → 需補讀）。"""

    url: str
    title: str = ""
    snippet: str = ""
    content: str | None = None

    @property
    def best_text(self) -> str:
        return (self.content or self.snippet or "").strip()


class SearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list["SearchResult"]: ...


class TavilyProvider:
    """主要來源：呼叫 Tavily Search API。任何錯誤都回空 list 讓上層降級。"""

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

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._api_key:
            return []
        try:
            from tavily import TavilyClient
        except Exception as exc:  # 套件沒裝 → 降級
            logger.warning(f"tavily 套件不可用，略過 Tavily：{exc}")
            return []
        try:
            client = TavilyClient(api_key=self._api_key)
            kwargs = {
                "search_depth": self._search_depth,
                "max_results": int(max_results),
                "country": self._country,
            }
            try:
                resp = client.search(query, timeout=self._timeout, **kwargs)
            except TypeError:
                # 舊版 client 不吃 timeout / country
                kwargs.pop("country", None)
                resp = client.search(query, **kwargs)
            results = resp.get("results", []) if isinstance(resp, dict) else []
            out: list[SearchResult] = []
            for r in results:
                url = str(r.get("url", "")).strip()
                if not url:
                    continue
                content = str(r.get("content") or "")
                out.append(
                    SearchResult(
                        url=url,
                        title=str(r.get("title", "")),
                        snippet=content,
                        content=content or None,
                    )
                )
            return out
        except Exception as exc:
            logger.warning(f"Tavily 搜尋失敗，將降級到 ddgs：{exc}")
            return []


class DdgsProvider:
    """備援來源：ddgs（DuckDuckGo）。免 key，通常只有短摘要 → content=None。"""

    def __init__(self, *, timeout: int = SEARCH_TIMEOUT_S) -> None:
        self._timeout = int(timeout)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            try:
                from ddgs import DDGS
            except Exception:
                from duckduckgo_search import DDGS  # 舊套件名
        except Exception as exc:
            logger.warning(f"ddgs 套件不可用：{exc}")
            return []
        try:
            out: list[SearchResult] = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=int(max_results)):
                    url = str(r.get("href") or r.get("url") or "").strip()
                    if not url:
                        continue
                    body = str(r.get("body") or "")
                    out.append(
                        SearchResult(
                            url=url, title=str(r.get("title", "")), snippet=body, content=None
                        )
                    )
            return out
        except Exception as exc:
            logger.warning(f"ddgs 搜尋失敗：{exc}")
            return []


class FallbackSearchProvider:
    """依序試多個 provider，回第一個非空結果；全空回空。單一 provider 出錯不打穿。"""

    def __init__(self, providers: list[SearchProvider]) -> None:
        self._providers = list(providers)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        for provider in self._providers:
            try:
                results = provider.search(query, max_results)
            except Exception as exc:
                logger.warning(f"搜尋 provider 出錯，換下一個：{exc}")
                results = []
            if results:
                return results
        return []


def build_search_provider(
    tavily_key: str, *, search_depth: str = DEFAULT_SEARCH_DEPTH
) -> SearchProvider:
    """有 Tavily key → Tavily 主 + ddgs 備援；沒 key → 只用 ddgs。"""
    key = (tavily_key or "").strip()
    if key:
        return FallbackSearchProvider(
            [TavilyProvider(key, search_depth=search_depth), DdgsProvider()]
        )
    return DdgsProvider()


# ── 注入防護（硬規則）──────────────────────────────────────────
_INJECTION_LINE_RE = re.compile(
    r"(忽略(以上|前面|先前).{0,6}(指示|指令|要求))"
    r"|(ignore\s+(all\s+)?previous)"
    r"|(system\s+prompt)"
    r"|(you\s+are\s+now)"
    r"|(disregard\s+the\s+above)",
    re.IGNORECASE,
)


def sanitize_source_text(text: str) -> str:
    """逐行剝掉命中注入樣式的行後才進 LLM。先上這組、觀察，避免過度誤殺。"""
    if not text:
        return ""
    kept = [ln for ln in text.splitlines() if not _INJECTION_LINE_RE.search(ln)]
    return "\n".join(kept)
