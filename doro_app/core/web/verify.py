"""查證 / 查資料管線（第 2 層）。

流程：**搜尋 API 找來源 → 摘要夠料就直接比對，不夠才用瀏覽器補讀 → 一次比對 → 誠實回報**。

- 搜尋改走 :class:`SearchProvider`（Tavily 主 / ddgs 備援），**不再爬 Bing HTML**。
- 「夠料」判定：至少 ``MIN_GOOD_SOURCES`` 個來源的摘要 ≥ ``MIN_SNIPPET_CHARS`` 字 → 免補讀。
- **瀏覽器懶開**：只有真的要補讀時才呼叫 ``session_provider()``——結構上擋掉提前開瀏覽器。
- **補讀失敗仍硬答**：補讀不成、但手上有 title/摘要，就照樣送進比對並標
  :data:`SUMMARY_ONLY_MARKER`；只有「連 title/摘要都空」才回「讀不到」。
- 只讀不點不送出（read-only），不受操作總開關限制。
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
SUMMARY_ONLY_MARKER = "【此來源可能只有摘要】"  # 補讀失敗、只有短摘要時標這行

# 挑來源時要跳過的網域（搜尋引擎自己、追蹤、社群、無關）。比對用「等於或 .結尾」。
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


def _is_skipped(dom: str) -> bool:
    return any(dom == skip or dom.endswith("." + skip) for skip in _SKIP_DOMAINS)


def pick_sources(results: list[SearchResult], limit: int = PICK_CANDIDATES) -> list[SearchResult]:
    """挑候選來源：**先依 score 排序**，再跳過搜尋引擎/社群、每網域一個、取前 *limit* 個。"""
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


class VerifyPipeline:
    """跑「搜尋 API → 夠料直接比對／不夠才補讀 → 比對」的查證流程。"""

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

        self._emit_progress("doro 上網幫你找找看…📡")
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
        chosen: list[dict] = []
        if len(good) >= MIN_GOOD_SOURCES:
            for s in good[: self._target]:
                chosen.append(self._as_source(s, summary_only=False))
            _dbg(f"{len(good)} 個來源摘要夠料 → 免補讀（0 goto）")
        else:
            for s in good:
                chosen.append(self._as_source(s, summary_only=False))
            remaining = [s for s in picked if s not in good]
            if remaining and len(chosen) < self._target:
                self._emit_progress("資料有點少，doro 開頁看仔細一點…📖")
                for s in remaining:
                    if len(chosen) >= self._target:
                        break
                    filled = self._read_source(s)
                    if filled is not None:
                        chosen.append(self._as_source(filled, summary_only=False))
                    elif s.best_text.strip() or (s.title or "").strip():
                        # 補讀失敗，但手上有 title/摘要 → 硬答（標記可能只有摘要）
                        chosen.append(self._as_source(s, summary_only=True))

        sources: list[dict] = []
        for c in chosen:
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

    # ── helpers ────────────────────────────────────────────
    def _emit_progress(self, text: str) -> None:
        try:
            self._progress(text)
        except Exception as exc:  # 進度顯示失敗不該影響最終答案
            _dbg(f"emit_progress failed: {exc}")

    @staticmethod
    def _as_source(s: SearchResult, *, summary_only: bool) -> dict:
        return {"text": s.best_text, "title": s.title, "url": s.url, "summary_only": summary_only}

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
