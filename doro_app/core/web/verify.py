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
    MIN_SNIPPET_CHARS,
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

# 「幫我找東西給我看」才開頁；純查證（是誰、真假）不開。
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
    """人是要「找東西看」而不只是問真假？"""
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
    lines.append(f"使用者想查證／了解：{query}")
    lines.append("")
    lines.append("以下是 doro 從網路上找到的幾個來源，請你比對它們後用繁體中文回答：")
    for i, src in enumerate(sources, 1):
        lines.append("")
        lines.append(f"【來源{i}】{src.get('title') or '(無標題)'}")
        lines.append(f"網址：{src.get('url')}")
        lines.append(src.get("text", "")[:_PER_SOURCE_CHARS])
    lines.append("")
    lines.append("回答要求：")
    lines.append("1. 綜合各來源回答使用者的問題，並在關鍵處標明是哪個來源說的。")
    lines.append("2. 說明來源之間『一致還是有出入』；若彼此矛盾，把不同說法都講出來。")
    lines.append(
        "3. 這些來源不足以回答、或找不到，就【老實說找不到/不確定】，絕對不要編；"
        f"標了「{SUMMARY_ONLY_MARKER}」的來源只有摘要、內容可能不完整，別當成完整證據。"
    )
    lines.append("4. 用純文字、不要 Markdown；開頭加一個 (狀態)。")
    lines.append(
        "5. 【務必簡潔】doro 是小小的桌面寵物，只用 2～4 句話講重點就好，"
        "大約 150 字以內；不要條列一大串、不要逐一交代每個來源。抓最重要的結論講給人聽即可。"
    )
    return "\n".join(lines)


def _has_search_text(s: SearchResult) -> bool:
    return bool((s.best_text or "").strip() or (s.title or "").strip())


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

        chosen: list[dict] = []
        empty: list[SearchResult] = []
        for s in picked:
            if _has_search_text(s):
                long_enough = len(s.best_text) >= MIN_SNIPPET_CHARS
                chosen.append(self._as_source(s, summary_only=not long_enough))
            else:
                empty.append(s)

        if empty and len(chosen) < self._target:
            self._emit_progress("資料有點少，doro 開頁看仔細一點…📖")
            for s in empty:
                if len(chosen) >= self._target:
                    break
                filled = self._read_source(s)
                if filled is not None:
                    chosen.append(self._as_source(filled, summary_only=False))

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
        answer = self._ask_llm(build_verify_prompt(query, sources)) or ""
        _dbg(f"answer len={len(answer)}")
        self._final(answer.strip() or "doro查完了，但一時整理不出來…要不要換個問法？")

        # 查證本身不開窗；「找給我看」才用與讀頁相同的 goto把第一個能開的網址打開。
        if looks_like_show_query(query) and self.found_urls:
            self._open_first_ok(self.found_urls)

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
            return session.snapshot(wait_idle=wait_idle)
        except TypeError:
            return session.snapshot()

    def _open_first_ok(self, urls: list[str]) -> None:
        """用讀頁同款的 goto 開第一張不是驗證的頁，留給人看。"""
        self._emit_progress("doro 把找到的頁打開給你看…")
        session = self._session_provider()
        if session.ensure_open():
            return
        for url in urls:
            _dbg(f"open for user: {url}")
            if self._goto(session, url, VERIFY_NAV_TIMEOUT_MS):
                self._abandon_page(session)
                continue
            view = self._snapshot(session, wait_idle=False)
            if not view.ok or looks_like_captcha(view) or looks_like_login_wall(view):
                if looks_like_captcha(view):
                    self._emit_progress("這站要驗證，doro 換下一個…")
                self._abandon_page(session)
                continue
            self.keep_browser = True
            return

    def _read_source(self, s: SearchResult) -> SearchResult | None:
        _dbg(f"補讀：{s.url}")
        session = self._session_provider()
        if session.ensure_open():
            return None
        if self._goto(session, s.url, VERIFY_NAV_TIMEOUT_MS):
            self._abandon_page(session)
            return None
        view = self._snapshot(session, wait_idle=False)
        if not view.ok or looks_like_captcha(view) or looks_like_login_wall(view):
            if looks_like_captcha(view):
                self._emit_progress("這站要驗證，doro 換下一個…")
            self._abandon_page(session)
            return None
        text = (view.text or "").strip()
        if not text:
            self._abandon_page(session)
            return None
        return SearchResult(
            url=view.url or s.url, title=view.title or s.title, snippet="", content=text
        )
