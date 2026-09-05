"""一個「開著不關、可以連續操作」的瀏覽器工作階段（第 3 層操作的引擎）。

跟 :class:`~doro_app.core.web.reader.WebPageReader`（讀一次就關）不同，
``WebSession`` 打開後會一直留著，讓 doro 一步一步操作：看目前頁面 → 點/打字/捲動
→ 再看新頁面。

重要限制（給之後接線的人）：
- Playwright 的 sync API **綁定建立它的那條執行緒**，跨執行緒呼叫會報錯。所以整個
  ``WebSession`` 從開到關，必須固定在**同一條背景執行緒**上使用（不要用
  QThreadPool 每個動作換一條）。接線層會用一條專屬執行緒＋命令佇列來驅動它。
- 所有方法都會**阻塞**，不可在 Qt 主執行緒直接呼叫。
- 用 doro 專屬設定檔（登入狀態留在那，跟使用者平常的 Chrome 分開）。

``snapshot()`` 會替目前頁面上「可點 / 可打字」的元件編號（塞一個 data-doro-idx
屬性），回傳含編號、角色、名稱的清單，之後 ``click_index`` / ``type_index`` 就靠這
個編號指定目標。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...utils.logger import get_logger
from .reader import DEFAULT_MAX_CHARS, DEFAULT_NAV_TIMEOUT_MS, _collapse_whitespace
from .web_actions import WebAction

logger = get_logger(__name__)

# snapshot 時掃描這些元件當作「可互動」。
_SNAPSHOT_JS = r"""
() => {
  const sel = 'a, button, input, textarea, select, [role=button], [role=link], [onclick]';
  const nodes = Array.from(document.querySelectorAll(sel));
  const out = [];
  let idx = 0;
  for (const el of nodes) {
    // 只收看得見的
    const rect = el.getClientRects();
    if (!rect || rect.length === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || tag;
    let name = (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      (el.value && String(el.value)) ||
      (el.innerText && el.innerText.trim()) ||
      el.getAttribute('title') ||
      el.getAttribute('alt') ||
      el.getAttribute('name') ||
      ''
    ).replace(/\s+/g, ' ').trim().slice(0, 80);
    el.setAttribute('data-doro-idx', String(idx));
    out.push({ idx, tag, role, name });
    idx++;
  }
  return out;
}
"""


# 抓目前頁面上看得見、有文字的外部連結（給查證挑來源）。
_LINKS_JS = r"""
() => {
  const seen = new Set();
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href || '';
    if (!/^https?:\/\//i.test(href)) continue;
    const text = (a.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text || text.length < 4) continue;
    if (seen.has(href)) continue;
    const rect = a.getClientRects();
    if (!rect || rect.length === 0) continue;
    seen.add(href);
    out.push({ url: href, text: text.slice(0, 140) });
    if (out.length >= 60) break;
  }
  return out;
}
"""


@dataclass
class PageView:
    """目前頁面的快照，給 LLM 決定下一步用。"""

    url: str = ""
    title: str = ""
    text: str = ""
    elements: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def element_names(self) -> dict[int, str]:
        """編號 → 名稱 對照（安全分級判斷點擊時用）。"""
        names: dict[int, str] = {}
        for el in self.elements:
            try:
                names[int(el["idx"])] = str(el.get("name", ""))
            except (KeyError, ValueError, TypeError):
                continue
        return names


class WebSession:
    """一個持續開著、可連續操作的瀏覽器。單一執行緒使用。"""

    def __init__(
        self,
        user_data_dir: Path,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        headless: bool = False,
        nav_timeout_ms: int = DEFAULT_NAV_TIMEOUT_MS,
        browser_channel: str | None = "chrome",
    ) -> None:
        self._user_data_dir = Path(user_data_dir)
        self._max_chars = max(500, int(max_chars))
        self._headless = bool(headless)
        self._nav_timeout_ms = int(nav_timeout_ms)
        # 優先用電腦裡真正的 Chrome（相容性較好）；開不起來就退回 Playwright 內建
        # 的 Chromium。設 None 直接用內建 Chromium。
        self._browser_channel = browser_channel

        self._pw = None
        self._context = None
        self._page = None

    def _launch_context(self, channel: str | None):
        kwargs = dict(
            user_data_dir=str(self._user_data_dir),
            headless=self._headless,
            # 關掉「未正確關閉／要還原網頁嗎」的還原泡泡、首次執行提示等干擾。
            args=[
                "--hide-crash-restore-bubble",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        if channel:
            kwargs["channel"] = channel
        return self._pw.chromium.launch_persistent_context(**kwargs)

    # ------------------------------------------------------------------ 生命週期

    @property
    def is_open(self) -> bool:
        """瀏覽器是不是還活著（使用者可能已手動把視窗關掉）。"""
        if self._page is None:
            return False
        try:
            return not self._page.is_closed()
        except Exception:
            return False

    def ensure_open(self) -> str | None:
        """確保瀏覽器已開。成功回 ``None``，失敗回錯誤訊息。

        若之前開過、但被使用者手動關掉了，會先清掉死掉的參照再重新開一個。
        """
        if self.is_open:
            return None
        # 有殘留的死參照（視窗被關）→ 先收乾淨，等下重新開。
        if self._page is not None or self._context is not None or self._pw is not None:
            self.close()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return (
                "doro 還不會開瀏覽器操作，要先安裝 Playwright：\n"
                "  pip install playwright\n  playwright install chromium\n裝好再重開 doro。"
            )
        try:
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
            self._pw = sync_playwright().start()
            try:
                self._context = self._launch_context(self._browser_channel)
                if self._browser_channel:
                    logger.info(f"WebSession 用真 Chrome（channel={self._browser_channel}）")
            except Exception as exc:
                # 沒裝 Chrome / 該 channel 開不起來 → 退回內建 Chromium。
                if self._browser_channel:
                    logger.warning(f"用 channel={self._browser_channel} 開失敗，改用內建 Chromium：{exc}")
                    self._context = self._launch_context(None)
                else:
                    raise
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._page.set_default_timeout(self._nav_timeout_ms)
            logger.info("WebSession 開啟成功")
            return None
        except Exception as exc:
            logger.error(f"WebSession 開啟失敗：{exc}", exc_info=True)
            self.close()
            return f"打開操作用瀏覽器失敗：{exc}"

    def close(self) -> None:
        """關掉瀏覽器、釋放資源。可重複呼叫。"""
        for closer in (
            lambda: self._context and self._context.close(),
            lambda: self._pw and self._pw.stop(),
        ):
            try:
                closer()
            except Exception as exc:
                logger.debug(f"WebSession 關閉時忽略錯誤：{exc}")
        self._pw = self._context = self._page = None

    # ------------------------------------------------------------------ 觀察

    def snapshot(self) -> PageView:
        """讀目前頁面：網址、標題、文字、可互動元件清單（含編號）。"""
        if not self.is_open:
            return PageView(error=self._closed_error())
        try:
            try:
                self._page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            url = self._page.url
            title = (self._page.title() or "").strip()
            elements = self._page.evaluate(_SNAPSHOT_JS)
            body_text = self._page.inner_text("body")
        except Exception as exc:
            logger.error(f"snapshot 失敗：{exc}")
            return PageView(error=self._error_or_closed(exc, "讀目前頁面"))

        text = _collapse_whitespace(body_text or "")
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + "\n\n……（內容太長，只讀前面這段）"
        return PageView(url=url, title=title, text=text, elements=elements or [])

    def collect_links(self) -> list[dict]:
        """抓目前頁面上「看得見、有文字」的外部 http(s) 連結（給查證挑來源用）。

        回傳 [{url, text}]，已依網址去重、最多 60 個。讀不到就回空清單。
        """
        if not self.is_open:
            return []
        try:
            return self._page.evaluate(_LINKS_JS) or []
        except Exception as exc:
            logger.debug(f"collect_links 失敗：{exc}")
            return []

    # ------------------------------------------------------------------ 操作

    def goto(self, url: str) -> str | None:
        return self._guard(
            lambda: self._page.goto(
                url, wait_until="domcontentloaded", timeout=self._nav_timeout_ms
            ),
            f"打開 {url}",
        )

    def click_index(self, index: int) -> str | None:
        return self._guard(
            lambda: self._page.click(f'[data-doro-idx="{int(index)}"]'),
            f"點第 {index} 個元件",
        )

    def type_index(self, index: int, text: str) -> str | None:
        return self._guard(
            lambda: self._page.fill(f'[data-doro-idx="{int(index)}"]', text),
            f"在第 {index} 個欄位輸入",
        )

    def press(self, key: str) -> str | None:
        return self._guard(lambda: self._page.keyboard.press(key), f"按下 {key}")

    def scroll(self, direction: str) -> str | None:
        dy = 600 if direction.strip().lower() != "up" else -600
        return self._guard(lambda: self._page.mouse.wheel(0, dy), f"捲動 {direction}")

    def back(self) -> str | None:
        return self._guard(lambda: self._page.go_back(), "回上一頁")

    def execute(self, action: WebAction) -> str | None:
        """執行一個 :class:`WebAction`。成功回 ``None``，失敗回錯誤訊息。

        ``done`` 不是真的操作（代表結束），這裡當 no-op 回 ``None``。
        """
        verb = action.verb
        if verb == "goto":
            return self.goto(action.params.get("url", ""))
        if verb == "click":
            idx = action.index()
            return "不知道要點哪個編號。" if idx is None else self.click_index(idx)
        if verb == "type":
            idx = action.index()
            if idx is None:
                return "不知道要在哪個編號的欄位打字。"
            return self.type_index(idx, action.params.get("text", ""))
        if verb == "press":
            return self.press(action.params.get("key", ""))
        if verb == "scroll":
            return self.scroll(action.params.get("dir", "down"))
        if verb == "back":
            return self.back()
        if verb == "done":
            return None
        return f"不認得的動作：{verb}"

    # ------------------------------------------------------------------ 內部

    def _guard(self, fn, what: str) -> str | None:
        """執行一個操作，成功回 ``None``，失敗回一句給人看的錯誤。"""
        if not self.is_open:
            return self._closed_error()
        try:
            fn()
            return None
        except Exception as exc:
            logger.error(f"{what} 失敗：{exc}")
            return self._error_or_closed(exc, what)

    # 使用者手動關掉視窗時，各種 Playwright 錯誤字樣。
    _CLOSED_MARKERS = (
        "has been closed", "target closed", "target page, context or browser",
        "browser has been closed", "page has been closed", "connection closed",
        "disconnected", "crashed", "browser is closed",
    )

    def _looks_closed(self, text: str) -> bool:
        low = (text or "").lower()
        return (not self.is_open) or any(m in low for m in self._CLOSED_MARKERS)

    def _closed_error(self) -> str:
        """視窗被關掉時的統一訊息，並順手重置（下次會重新開一個）。"""
        self.close()
        return "瀏覽器視窗好像被關掉了～doro這次先停，下次會自動重新開一個喔。"

    def _error_or_closed(self, exc: Exception, what: str) -> str:
        if self._looks_closed(str(exc)):
            return self._closed_error()
        return f"{what}出錯了：{str(exc)[:150]}"
