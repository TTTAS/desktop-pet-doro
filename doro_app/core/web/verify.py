"""查證 / 查資料管線（第 2 層）。"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Callable, Protocol

from ...utils.logger import get_logger
from .operator import looks_like_captcha, looks_like_login_wall
from .search_providers import (
    MAX_RESULTS,
    TARGET_SOURCES,
    SearchProvider,
    SearchResult,
    sanitize_source_text,
    search_backend_name,
)
from .session import PageView

logger = get_logger(__name__)

DEFAULT_MAX_SOURCES = TARGET_SOURCES
PICK_CANDIDATES = 5
_PER_SOURCE_CHARS = 2000
SUMMARY_ONLY_MARKER = "【此來源可能只有摘要】"
VERIFY_NAV_TIMEOUT_MS = 10_000
_BLANK = "about:blank"
MAX_OPEN_TABS = 3

_SHOW_QUERY_RE = re.compile(
    r"找|尋找|買|購買|產品|商品|周邊|推薦|給我看|秀給|哪裡有|有沒有賣|shop|buy|product",
    re.IGNORECASE,
)

_SKIP_DOMAINS = (
    "bing.com",
    "microsoft.com",
    "microsofttranslator.com",
    "msn.com",
    "go.microsoft.com",
    "google.com",
    "googleadservices.com",
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "t.co",
    "w3.org",
    "schema.org",
    "aka.ms",
    "live.com",
    "duckduckgo.com",
)

_DEBUG = os.environ.get("DORO_WEB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[doro verify] {msg}", flush=True)


def looks_like_show_query(query: str) -> bool:
    return bool(_SHOW_QUERY_RE.search((query or "").strip()))


class SessionLike(Protocol):
    def ensure_open(self) -> str | None: ...
    def goto(self, url: str, timeout_ms: int | None = None) -> str | None: ...
    def snapshot(self, wait_idle: bool = True) -> PageView: ...


AskLLM = Callable[[str], str]
Emit = Callable[[str], None]
SessionProvider = Callable[[], SessionLike]


def _domain(url: str) -> str:
    try:
        net = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def _is_skipped(dom: str) -> bool:
    return any(dom == skip or dom.endswith("." + skip) for skip in _SKIP_DOMAINS)


def pick_sources(results: list[SearchResult], limit: int = PICK_CANDIDATES) -> list[SearchResult]:
    ranked = sorted(results, key=lambda r: (r.score or 0.0), reverse=True)
    picked: list[SearchResult] = []
    seen: set[str] = set()
    for r in ranked:
        dom = _domain(r.url)
        if not dom or _is_skipped(dom) or dom in seen:
            continue
        seen.add(dom)
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


def build_verify_prompt(query: str, sources: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"使用者的搜尋任務：{query}")
    lines.append("")
    lines.append("以下是讀到的分頁或搜尋摘要；有摘要標記的來源未取得正文，請誠實區分：")
    for i, src in enumerate(sources, 1):
        lines.append("")
        lines.append(f"【來源{i}】{src.get('title') or '(無標題)'}")
        lines.append(f"網址：{src.get('url')}")
        lines.append(src.get("text", "")[:_PER_SOURCE_CHARS])
    lines.append("")
    lines.append("回答要求：")
    lines.append(
        "1. 依任務目的作答：探索／推薦就挑具體候選並說明特色或理由；查資料就回答問題；查證真偽才比對證據與矛盾。"
    )
    lines.append(
        "2. 考慮各個分頁，挑相關內容，不必硬湊推薦數量。提到候選時用實際名稱，可附提供的網址，不要寫「來源1」「來源2」。"
    )
    lines.append("3. 不足就說不確定，絕不要編。")
    lines.append("4. 純文字；開頭 (狀態)；2～4 句，約 150 字。")
    return "\n".join(lines)


def _has_search_text(s: SearchResult) -> bool:
    return bool((s.best_text or "").strip() or (s.title or "").strip())


def _fallback_speech(sources: list[dict]) -> str:
    names = [(s.get("title") or s.get("url") or "一頁").strip() for s in sources]
    names = [n for n in names if n][:3]
    opened = "、".join(names) if names else "幾個分頁"
    return f"doro把頁打開了，但整理回覆時卡住了。人先自己看分頁吧～開了：{opened}"


class VerifyPipeline:
    def __init__(
        self,
        search_provider: SearchProvider,
        session_provider: SessionProvider,
        ask_llm: AskLLM,
        emit_progress: Emit,
        emit_final: Emit,
        *,
        max_sources: int = DEFAULT_MAX_SOURCES,
    ) -> None:
        self._search = search_provider
        self._session_provider = session_provider
        self._ask_llm = ask_llm
        self._progress = emit_progress
        self._final = emit_final
        self._target = max(1, int(max_sources))
        self.found_urls: list[str] = []
        self.keep_browser = False

    def run(self, query: str) -> None:
        query = (query or "").strip()
        if not query:
            self._final("人要doro查什麼呀？再說清楚一點嘛～")
            return

        self._emit_progress("doro 上網幫你找找看…📡")
        _dbg(f"search: {query}")
        try:
            raw = self._search.search(query, MAX_RESULTS)
        except Exception as exc:
            _dbg(f"search provider raised: {exc}")
            raw = []

        backend = search_backend_name(self._search)
        _dbg(f"search via {backend}: raw={len(raw)}")
        if raw:
            self._emit_progress(f"用 {backend} 找到來源…📡")

        picked = pick_sources(raw)
        self.found_urls = [r.url for r in picked]
        _dbg(f"picked {len(picked)} candidates: {self.found_urls}")
        if not picked:
            self._final("唔…doro找不到適合的來源耶。換個關鍵字再試試？")
            return

        tab_reads = self._open_and_read(self.found_urls[:MAX_OPEN_TABS])

        chosen: list[dict] = []
        seen_urls: set[str] = set()
        for s in tab_reads[: self._target]:
            chosen.append(self._as_source(s, summary_only=False))
            seen_urls.add(s.url)
        if len(chosen) < self._target:
            for s in picked:
                if s.url in seen_urls or not _has_search_text(s):
                    continue
                # Text length does not prove that the browser read the source.
                chosen.append(self._as_source(s, summary_only=True))
                seen_urls.add(s.url)
                if len(chosen) >= self._target:
                    break

        sources: list[dict] = []
        for c in chosen[: self._target]:
            text = sanitize_source_text(c["text"])
            if c["summary_only"]:
                text = (SUMMARY_ONLY_MARKER + "\n" + text).strip()
            if text.strip() or (c["title"] or "").strip():
                sources.append({"title": c["title"], "url": c["url"], "text": text})

        if not sources:
            self._final("找到的來源doro都讀不到（可能要登入或擋機器人）…這題先查不到耶，抱歉啦～")
            return

        _dbg(f"比對 {len(sources)} 個來源")
        try:
            answer = self._ask_llm(build_verify_prompt(query, sources)) or ""
        except Exception as exc:
            print(f"[doro verify] llm failed: {exc}", flush=True)
            answer = ""
        _dbg(f"answer len={len(answer)}")
        self._final(answer.strip() or _fallback_speech(sources))

    def _emit_progress(self, text: str) -> None:
        try:
            self._progress(text)
        except Exception as exc:
            _dbg(f"emit_progress failed: {exc}")

    @staticmethod
    def _as_source(s: SearchResult, *, summary_only: bool) -> dict:
        return {"text": s.best_text, "title": s.title, "url": s.url, "summary_only": summary_only}

    def _abandon_page(self, session: SessionLike) -> None:
        try:
            session.goto(_BLANK, timeout_ms=3_000)
        except TypeError:
            try:
                session.goto(_BLANK)
            except Exception as exc:
                _dbg(f"abandon page failed: {exc}")
        except Exception as exc:
            _dbg(f"abandon page failed: {exc}")

    def _goto(self, session: SessionLike, url: str, timeout_ms: int | None = None) -> str | None:
        try:
            return session.goto(url, timeout_ms=timeout_ms)
        except TypeError:
            return session.goto(url)

    def _snapshot(self, session: SessionLike, *, wait_idle: bool) -> PageView:
        try:
            try:
                return session.snapshot(wait_idle=wait_idle)
            except TypeError:
                return session.snapshot()
        except Exception as exc:
            print(f"[doro verify] snapshot raised: {exc}", flush=True)
            return PageView(error=str(exc))

    def _open_tab(self, session: SessionLike, url: str, *, extra: bool) -> bool:
        try:
            if extra and hasattr(session, "new_tab"):
                err = session.new_tab(url, timeout_ms=VERIFY_NAV_TIMEOUT_MS)
                if err:
                    print(f"[doro verify] tab failed: {url} ({err})", flush=True)
                    return False
                print(f"[doro verify] tab: {url}", flush=True)
                return True
            if self._goto(session, url, VERIFY_NAV_TIMEOUT_MS):
                print(f"[doro verify] goto failed: {url}", flush=True)
                return False
            return True
        except Exception as exc:
            print(f"[doro verify] open raised: {url} ({exc})", flush=True)
            return False

    def _view_as_result(self, view: PageView) -> SearchResult | None:
        if not getattr(view, "ok", False):
            print(
                f"[doro verify] skip tab (bad snapshot): {getattr(view, 'error', '')}", flush=True
            )
            return None
        if looks_like_captcha(view) or looks_like_login_wall(view):
            print(f"[doro verify] skip tab (block): {getattr(view, 'url', '')}", flush=True)
            return None
        text = (getattr(view, "text", None) or "").strip()
        if not text:
            return None
        print(f"[doro verify] read tab: {view.url}", flush=True)
        return SearchResult(
            url=view.url or "",
            title=getattr(view, "title", "") or "",
            snippet="",
            content=text,
        )

    def _open_and_read(self, urls: list[str]) -> list[SearchResult]:
        if not urls:
            return []
        self._emit_progress("doro 把找到的頁打開給你看…")
        print(f"[doro verify] open after pick: {urls}", flush=True)
        session = self._session_provider()
        err = session.ensure_open()
        if err:
            print(f"[doro verify] open failed: {err}", flush=True)
            return []
        out: list[SearchResult] = []
        opened = 0
        for i, url in enumerate(urls):
            print(f"[doro verify] open: {url}", flush=True)
            if not self._open_tab(session, url, extra=(i > 0)):
                continue
            opened += 1
            view = self._snapshot(session, wait_idle=False)
            filled = self._view_as_result(view)
            if filled is not None:
                out.append(filled)
        if opened:
            self.keep_browser = True
            print(f"[doro verify] opened {opened} tab(s), read {len(out)}", flush=True)
        return out
