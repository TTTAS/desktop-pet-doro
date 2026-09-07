"""查證 / 查資料管線（第 2 層）。

流程：**搜尋 API 找來源 → 摘要夠用就直接比對，不夠才用瀏覽器補讀 → 一次比對 → 誠實回報**。

跟舊版差別：
- 搜尋改走 :class:`SearchProvider`（Tavily 主 / ddgs 備援），**不再爬 Bing HTML**。
- 「夠用」判定：至少 ``MIN_GOOD_SOURCES`` 個來源的摘要 ≥ ``MIN_SNIPPET_CHARS`` 字 → 免補讀。
- **瀏覽器懶開**：只有真的要補讀時才呼叫 ``session_provider()``——結構上擋掉提前開瀏覽器。
- 只讀不點不送出（read-only），不受操作總開關限制。
- 用注入的 provider / session_provider / ask_llm / emit，純邏輯好測。
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Callable, Protocol

from ...utils.logger import get_logger
from .operator import looks_like_captcha, looks_like_login_wall
from .search_providers import (
    MAX_RESULTS,
    MIN_GOOD_SOURCES,
    MIN_SNIPPET_CHARS,
    TARGET_SOURCES,
    SearchProvider,
    SearchResult,
    sanitize_source_text,
)
from .session import PageView

logger = get_logger(__name__)

DEFAULT_MAX_SOURCES = TARGET_SOURCES  # 最終要幾個來源比對
PICK_CANDIDATES = 5  # 從搜尋結果挑幾個候選（供補讀用）
_PER_SOURCE_CHARS = 2000  # 每個來源最多取多少字餵給 AI

# 挑來源時要跳過的網域（搜尋引擎自己、追蹤、社群、無關）。
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


class SessionLike(Protocol):
    def ensure_open(self) -> str | None: ...
    def goto(self, url: str) -> str | None: ...
    def snapshot(self) -> PageView: ...


AskLLM = Callable[[str], str]
Emit = Callable[[str], None]
SessionProvider = Callable[[], SessionLike]


def _domain(url: str) -> str:
    try:
        net = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def pick_sources(results: list[SearchResult], limit: int = PICK_CANDIDATES) -> list[SearchResult]:
    """挑候選來源：跳過搜尋引擎/社群網域、每網域一個、取前 *limit* 個（保留原排序）。"""
    picked: list[SearchResult] = []
    seen: set[str] = set()
    for r in results:
        dom = _domain(r.url)
        if not dom or any(skip in dom for skip in _SKIP_DOMAINS):
            continue
        if dom in seen:
            continue
        seen.add(dom)
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


def build_verify_prompt(query: str, sources: list[dict]) -> str:
    """把使用者的問題 + 幾個來源的內容，組成給 AI 比對的提示。"""
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
    lines.append("3. 這些來源不足以回答、或找不到，就【老實說找不到/不確定】，絕對不要編。")
    lines.append("4. 用純文字、不要 Markdown；開頭加一個 (狀態)。")
    lines.append(
        "5. 【務必簡潔】doro 是小小的桌面寵物，只用 2～4 句話講重點就好，"
        "大約 150 字以內；不要條列一大串、不要逐一交代每個來源。抓最重要的結論講給人聽即可。"
    )
    return "\n".join(lines)


class VerifyPipeline:
    """跑「搜尋 API → 夠用直接比對／不夠才補讀 → 比對」的查證流程。"""

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
        self._session_provider = session_provider  # 真的要補讀才呼叫（懶開瀏覽器）
        self._ask_llm = ask_llm
        self._progress = emit_progress
        self._final = emit_final
        self._target = max(1, int(max_sources))

    def run(self, query: str) -> None:
        """對 *query* 跑完查證（阻塞，需在專屬背景執行緒呼叫）。"""
        query = (query or "").strip()
        if not query:
            self._final("人要doro查什麼呀？再說清楚一點嘛～")
            return

        _dbg(f"search: {query}")
        try:
            raw = self._search.search(query, MAX_RESULTS)
        except Exception as exc:  # provider 理論上自己吞錯；這裡再兜一層底
            _dbg(f"search provider raised: {exc}")
            raw = []

        picked = pick_sources(raw)
        _dbg(f"picked {len(picked)} candidates: {[r.url for r in picked]}")
        if not picked:
            self._final("唔…doro找不到適合的來源耶。換個關鍵字再試試？")
            return

        good = [s for s in picked if len(s.best_text) >= MIN_SNIPPET_CHARS]
        if len(good) >= MIN_GOOD_SOURCES:
            chosen = good[: self._target]
            _dbg(f"{len(good)} 個來源摘要夠料 → 免補讀（0 goto）")
        else:
            chosen = list(good)
            for s in picked:
                if len(chosen) >= self._target:
                    break
                if s in good:
                    continue
                filled = self._read_source(s)
                if filled is not None:
                    chosen.append(filled)

        sources: list[dict] = []
        for s in chosen:
            text = sanitize_source_text(s.best_text)
            if text.strip():
                sources.append({"title": s.title, "url": s.url, "text": text})

        if not sources:
            self._final("找到的來源doro都讀不到（可能要登入或擋機器人）…這題先查不到耶，抱歉啦～")
            return

        _dbg(f"比對 {len(sources)} 個來源")
        answer = self._ask_llm(build_verify_prompt(query, sources)) or ""
        _dbg(f"answer len={len(answer)}")
        self._final(answer.strip() or "doro查完了，但一時整理不出來…要不要換個問法？")

    def _read_source(self, s: SearchResult) -> SearchResult | None:
        """摘要不夠時，用瀏覽器補讀一個來源（此時才真的開瀏覽器）。讀不到回 None。"""
        _dbg(f"補讀：{s.url}")
        session = self._session_provider()
        if session.ensure_open():
            return None
        if session.goto(s.url):
            return None
        view = session.snapshot()
        if not view.ok or looks_like_captcha(view) or looks_like_login_wall(view):
            return None
        text = (view.text or "").strip()
        if not text:
            return None
        return SearchResult(
            url=view.url or s.url, title=view.title or s.title, snippet="", content=text
        )
