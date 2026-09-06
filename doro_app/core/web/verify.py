"""查證 / 查資料管線（第 2 層）。

跟「操作」不同：查證的重點是**找幾個來源、一次比對**。所以這裡走一條專屬流程：

    搜尋(Bing) → 抓前幾個結果連結 → 各讀一頁 → 把所有來源一起餵給 AI 比對 → 誠實回報

- 用 Bing（比較不會跳人機驗證）。
- 讀來源時碰到需要登入/驗證的就**跳過**（查證不必卡在單一來源），用讀得到的那些。
- 只讀不點不送出（read-only），所以不受操作總開關限制。
- 跟 :class:`WebOperator` 一樣用注入的 session/ask_llm/emit，好測。
"""

from __future__ import annotations

import base64
import os
import urllib.parse
from typing import Callable, Protocol

from ...utils.logger import get_logger
from .operator import looks_like_captcha, looks_like_login_wall
from .session import PageView

logger = get_logger(__name__)

DEFAULT_MAX_SOURCES = 3          # 最多讀幾個來源來比對
_PER_SOURCE_CHARS = 2000         # 每個來源最多取多少字餵給 AI

# 挑來源時要跳過的網域（搜尋引擎自己、追蹤、無關）。
_SKIP_DOMAINS = (
    "bing.com", "microsoft.com", "microsofttranslator.com", "msn.com",
    "go.microsoft.com", "google.com", "googleadservices.com", "youtube.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "t.co",
    "w3.org", "schema.org", "aka.ms", "live.com",
)

_DEBUG = os.environ.get("DORO_WEB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[doro verify] {msg}", flush=True)


class SessionLike(Protocol):
    def ensure_open(self) -> str | None: ...
    def goto(self, url: str) -> str | None: ...
    def snapshot(self) -> PageView: ...
    def collect_links(self) -> list[dict]: ...


AskLLM = Callable[[str], str]
Emit = Callable[[str], None]


def build_search_url(query: str) -> str:
    """組 Bing 搜尋結果頁網址。"""
    q = urllib.parse.quote((query or "").strip())
    return f"https://www.bing.com/search?q={q}"


def _domain(url: str) -> str:
    try:
        net = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def resolve_redirect(url: str) -> str:
    """把搜尋引擎的轉址連結還原成真正的目的地網址。

    Bing 的結果連結長 ``bing.com/ck/a?...&u=a1<base64url>``；Google 是
    ``/url?q=<url>``；DuckDuckGo 是 ``/l/?uddg=<url>``。還原不了就原樣回傳。
    """
    try:
        p = urllib.parse.urlparse(url)
    except ValueError:
        return url
    host = p.netloc.lower()
    qs = urllib.parse.parse_qs(p.query)
    if "bing.com" in host and qs.get("u", [""])[0].startswith("a1"):
        raw = qs["u"][0][2:]
        raw += "=" * (-len(raw) % 4)  # 補 base64 padding
        try:
            decoded = base64.urlsafe_b64decode(raw).decode("utf-8", "replace")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass
    if "google." in host and qs.get("q", [""])[0].startswith("http"):
        return urllib.parse.unquote(qs["q"][0])
    if "duckduckgo.com" in host and qs.get("uddg"):
        return urllib.parse.unquote(qs["uddg"][0])
    return url


def pick_result_links(links: list[dict], max_sources: int) -> list[dict]:
    """從搜尋頁抓到的一堆連結裡，挑出要當來源的。

    先把轉址還原成真正網址，再去掉搜尋引擎自己/社群，每個網域只取一個。
    """
    picked: list[dict] = []
    seen_domains: set[str] = set()
    for link in links:
        url = resolve_redirect(str(link.get("url", "")))
        dom = _domain(url)
        if not dom or any(skip in dom for skip in _SKIP_DOMAINS):
            continue
        if dom in seen_domains:
            continue
        seen_domains.add(dom)
        picked.append({"url": url, "text": str(link.get("text", ""))})
        if len(picked) >= max_sources:
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
    """跑「搜尋→讀多個來源→比對」的查證流程。"""

    def __init__(
        self,
        session: SessionLike,
        ask_llm: AskLLM,
        emit_progress: Emit,
        emit_final: Emit,
        *,
        max_sources: int = DEFAULT_MAX_SOURCES,
    ) -> None:
        self._session = session
        self._ask_llm = ask_llm
        self._progress = emit_progress
        self._final = emit_final
        self._max_sources = max(1, int(max_sources))

    def run(self, query: str) -> None:
        """對 *query* 跑完查證（阻塞，需在專屬背景執行緒呼叫）。"""
        query = (query or "").strip()
        if not query:
            self._final("人要doro查什麼呀？再說清楚一點嘛～")
            return

        err = self._session.ensure_open()
        if err:
            self._final(err)
            return

        # 機械進度只留後台（_dbg → 終端機），泡泡不顯示碎念——泡泡由 doro 那句
        # 可愛台詞撐著，查完直接換成答案。
        _dbg(f"search: {query}")
        goto_err = self._session.goto(build_search_url(query))
        if goto_err:
            self._final(f"連搜尋頁都打不開…（{goto_err}）")
            return

        search_view = self._session.snapshot()
        if not search_view.ok:
            self._final(search_view.error or "doro看不到搜尋結果…")
            return
        if looks_like_captcha(search_view) or looks_like_login_wall(search_view):
            self._final("搜尋這步就被網站擋住了…先換個說法、或等一下再試試看好嗎？")
            return

        raw_links = self._session.collect_links()
        _dbg(f"raw links from search page = {len(raw_links)}")
        results = pick_result_links(raw_links, self._max_sources)
        _dbg(f"picked {len(results)} sources: {[r['url'] for r in results]}")
        if not results:
            self._final("唔…doro找不到適合的來源耶。換個關鍵字再試試？")
            return

        sources: list[dict] = []
        for i, link in enumerate(results, 1):
            _dbg(f"讀第 {i}/{len(results)} 個來源：{link['url']}")
            if self._session.goto(link["url"]):
                _dbg(f"source {i} goto failed, skip")
                continue
            view = self._session.snapshot()
            if not view.ok or looks_like_captcha(view) or looks_like_login_wall(view):
                _dbg(f"source {i} blocked/failed, skip")
                continue
            if not (view.text or "").strip():
                continue
            sources.append({"title": view.title, "url": view.url, "text": view.text})

        if not sources:
            self._final("找到的來源doro都讀不到（可能要登入或擋機器人）…這題先查不到耶，抱歉啦～")
            return

        _dbg(f"讀完 {len(sources)} 個來源，開始比對")
        answer = self._ask_llm(build_verify_prompt(query, sources)) or ""
        _dbg(f"answer len={len(answer)}")
        self._final(answer.strip() or "doro查完了，但一時整理不出來…要不要換個問法？")
