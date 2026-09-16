"""一個「開著不關、可以連續操作」的瀏覽器工作階段。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...utils.logger import get_logger
from .reader import DEFAULT_MAX_CHARS, DEFAULT_NAV_TIMEOUT_MS, _collapse_whitespace
from .web_actions import WebAction

logger = get_logger(__name__)

_SNAPSHOT_JS = r"""
() => {
  const sel = 'a, button, input, textarea, select, [role=button], [role=link], [onclick]';
  const nodes = Array.from(document.querySelectorAll(sel));
  const out = [];
  let idx = 0;
  for (const el of nodes) {
    const rect = el.getClientRects();
    if (!rect || rect.length === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || tag;
    const input_type = (el.getAttribute('type') || '').toLowerCase();
    const sensitive = input_type === 'password' || /^(current-password|new-password|one-time-code)$/.test(el.getAttribute('autocomplete') || '');
    let name = sensitive ? '密碼或驗證碼（內容不提供）' : (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      (!['input', 'textarea', 'select'].includes(tag) && !el.isContentEditable && el.innerText && el.innerText.trim()) ||
      el.getAttribute('title') ||
      el.getAttribute('alt') ||
      el.getAttribute('name') ||
      ''
    ).replace(/\s+/g, ' ').trim().slice(0, 80);
    el.setAttribute('data-doro-idx', String(idx));
    const is_submit = !!el.form && ((tag === 'button' && (!input_type || input_type === 'submit')) || (tag === 'input' && ['submit', 'image'].includes(input_type)));
    out.push({ idx, tag, role, name, input_type, sensitive, is_submit,
      focused: el === document.activeElement });
    idx++;
  }
  return out;
}
"""

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
    url: str = ""
    title: str = ""
    text: str = ""
    elements: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def element_names(self) -> dict[int, str]:
        names: dict[int, str] = {}
        for el in self.elements:
            try:
                names[int(el["idx"])] = str(el.get("name", ""))
            except (KeyError, ValueError, TypeError):
                continue
        return names


class WebSession:
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
        self._browser_channel = browser_channel
        self._pw = None
        self._context = None
        self._page = None

    def _launch_context(self, channel: str | None):
        kwargs = dict(
            user_data_dir=str(self._user_data_dir),
            headless=self._headless,
            no_viewport=True,
            args=[
                "--hide-crash-restore-bubble",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
            ],
        )
        if channel:
            kwargs["channel"] = channel
        return self._pw.chromium.launch_persistent_context(**kwargs)

    @property
    def is_open(self) -> bool:
        pages = self.open_pages()
        if pages:
            if self._page is None or self._page.is_closed():
                self._page = pages[0]
            return True
        return False

    def open_pages(self) -> list:
        if self._context is None:
            return []
        try:
            return [p for p in self._context.pages if not p.is_closed()]
        except Exception:
            return []

    def use_page(self, page) -> None:
        self._page = page
        try:
            page.bring_to_front()
        except Exception:
            pass

    def ensure_open(self) -> str | None:
        if self.is_open:
            return None
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
                if self._browser_channel:
                    logger.warning(
                        f"用 channel={self._browser_channel} 開失敗，改用內建 Chromium：{exc}"
                    )
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
        for closer in (
            lambda: self._context and self._context.close(),
            lambda: self._pw and self._pw.stop(),
        ):
            try:
                closer()
            except Exception as exc:
                logger.debug(f"WebSession 關閉時忽略錯誤：{exc}")
        self._pw = self._context = self._page = None

    def snapshot(self) -> PageView:
        if not self.is_open:
            return PageView(error=self._closed_error())
        return self._snapshot_one(self._page, wait_idle=False)

    def snapshot_open_pages(self, *, wait_idle: bool = False) -> list[PageView]:
        views: list[PageView] = []
        for page in self.open_pages():
            views.append(self._snapshot_one(page, wait_idle=wait_idle))
        return views

    def _snapshot_one(self, page, *, wait_idle: bool) -> PageView:
        if page is None:
            return PageView(error="沒有頁可讀")
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                if wait_idle:
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except Exception:
                        pass
                url = page.url or ""
                if url.startswith("about:"):
                    return PageView(url=url, error="空白頁")
                title = (page.title() or "").strip()
                body_text = page.inner_text("body")
                try:
                    elements = page.evaluate(_SNAPSHOT_JS)
                except Exception:
                    elements = []
                text = _collapse_whitespace(body_text or "")
                if len(text) > self._max_chars:
                    text = text[: self._max_chars] + "\n\n……（內容太長，只讀前面這段）"
                return PageView(url=url, title=title, text=text, elements=elements or [])
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if attempt == 0 and ("context was destroyed" in msg or "execution context" in msg):
                    continue
                break
        logger.error(f"snapshot 失敗：{last_exc}")
        return PageView(error=self._error_or_closed(last_exc or RuntimeError("snapshot"), "讀目前頁面"))

    def collect_links(self) -> list[dict]:
        if not self.is_open:
            return []
        try:
            return self._page.evaluate(_LINKS_JS) or []
        except Exception as exc:
            logger.debug(f"collect_links 失敗：{exc}")
            return []

    def goto(self, url: str, timeout_ms: int | None = None) -> str | None:
        return self._guard(
            lambda: self._page.goto(
                url, wait_until="domcontentloaded", timeout=timeout_ms or self._nav_timeout_ms
            ),
            f"打開 {url}",
        )

    def new_tab(self, url: str, timeout_ms: int | None = None) -> str | None:
        if self.ensure_open():
            return "瀏覽器還沒開。"
        timeout = int(timeout_ms or self._nav_timeout_ms)
        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(timeout)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            self.use_page(page)
            return None
        except Exception as exc:
            logger.error(f"new_tab 失敗：{exc}")
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            return f"新分頁打不開：{str(exc)[:120]}"

    def click_index(self, index: int) -> str | None:
        return self._guard(
            lambda: self._page.click(f'[data-doro-idx="{int(index)}"]'),
            f"點第 {index} 個元件",
        )

    def type_index(self, index: int, text: str) -> str | None:
        if not self.is_open:
            return self._closed_error()
        try:
            locator = self._page.locator(f'[data-doro-idx="{int(index)}"]')
            sensitive = locator.evaluate("el => el.type === 'password' || /^(current-password|new-password|one-time-code)$/.test(el.autocomplete || '')")
            if sensitive:
                return "密碼或驗證碼請使用者自行輸入。"
            locator.fill(text)
            return None
        except Exception:
            # Playwright's exception call log may include the filled text.
            logger.warning("欄位輸入失敗（不記錄輸入內容）")
            return "欄位輸入失敗，請重新讀取頁面後再試。"

    def press(self, key: str) -> str | None:
        return self._guard(lambda: self._page.keyboard.press(key), f"按下 {key}")

    def scroll(self, direction: str) -> str | None:
        dy = 600 if direction.strip().lower() != "up" else -600
        return self._guard(lambda: self._page.mouse.wheel(0, dy), f"捲動 {direction}")

    def back(self) -> str | None:
        return self._guard(lambda: self._page.go_back(), "回上一頁")

    def execute(self, action: WebAction) -> str | None:
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

    def _guard(self, fn, what: str) -> str | None:
        if not self.is_open:
            return self._closed_error()
        try:
            fn()
            return None
        except Exception as exc:
            logger.error(f"{what} 失敗：{exc}")
            return self._error_or_closed(exc, what)

    _CLOSED_MARKERS = (
        "has been closed",
        "target closed",
        "target page, context or browser",
        "browser has been closed",
        "page has been closed",
        "connection closed",
        "disconnected",
        "crashed",
        "browser is closed",
    )

    def _looks_closed(self, text: str) -> bool:
        low = (text or "").lower()
        return (not self.is_open) or any(m in low for m in self._CLOSED_MARKERS)

    def _closed_error(self) -> str:
        self.close()
        return "瀏覽器視窗好像被關掉了～doro這次先停，下次會自動重新開一個喔。"

    def _error_or_closed(self, exc: Exception, what: str) -> str:
        if self._looks_closed(str(exc)):
            return self._closed_error()
        return f"{what}出錯了：{str(exc)[:150]}"
