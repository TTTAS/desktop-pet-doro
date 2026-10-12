"""一個「開著不關、可以連續操作」的瀏覽器工作階段。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...utils.logger import get_logger
from .reader import DEFAULT_MAX_CHARS, DEFAULT_NAV_TIMEOUT_MS, _collapse_whitespace
from .web_actions import TARGET_VERBS, WebAction, WebStep, valid_web_url

logger = get_logger(__name__)

# The same descriptor is used when observing and immediately before executing.
# Never include input values in labels or in the data sent to the model.
_ELEMENT_INFO_JS = r"""
el => {
  if (!el.isConnected || !el.getClientRects().length) return null;
  const style = getComputedStyle(el);
  if (style.visibility !== 'visible' || style.display === 'none') return null;
  const tag = el.tagName.toLowerCase();
  const input_type = (el.getAttribute('type') || '').toLowerCase();
  const sensitive = input_type === 'password' || /^(current-password|new-password|one-time-code)$/.test(el.autocomplete || '');
  const clean = text => (text || '').replace(/\s+/g, ' ').trim();
  const labelText = label => {
    const clone = label.cloneNode(true);
    clone.querySelectorAll('input,textarea,select,[contenteditable],script,style,[hidden]').forEach(node => node.remove());
    return clone.textContent;
  };
  const editable = el.isContentEditable || !!el.querySelector('input,textarea,[contenteditable]');
  const name = sensitive ? '密碼或驗證碼（內容不提供）' : clean(
    el.getAttribute('aria-label') ||
    (el.labels && Array.from(el.labels, labelText).join(' ')) ||
    el.getAttribute('placeholder') ||
    (!['input', 'textarea', 'select'].includes(tag) && !editable && el.innerText) ||
    el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || ''
  ).slice(0, 80);
  const rect = el.getBoundingClientRect();
  return {
    tag, role: el.getAttribute('role') || tag, name, input_type, sensitive,
    is_submit: !!el.form && ((tag === 'button' && (!input_type || input_type === 'submit')) || (tag === 'input' && ['submit', 'image'].includes(input_type))),
    disabled: el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true',
    checked: ['checkbox', 'radio'].includes(input_type) ? el.checked : null,
    options: tag === 'select' ? Array.from(el.options).slice(0, 50).map(o => ({label: o.label, disabled: o.disabled || !!o.closest('optgroup:disabled')})) : [],
    multiple: !!el.multiple,
    href: tag === 'a' ? el.href : '',
    form_action: el.form ? el.formAction || el.form.action : '',
    focused: el === document.activeElement,
    in_viewport: rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
  };
}
"""

_CAPTURE_JS = (
    """() => {
  const describe = """
    + _ELEMENT_INFO_JS
    + """;
  document.querySelectorAll('[data-doro-idx]').forEach(el => el.removeAttribute('data-doro-idx'));
  const nodes = document.querySelectorAll('a, button, input, textarea, select, [contenteditable=true], [role=button], [role=link], [onclick]');
  const out = [];
  const handles = [];
  for (const el of nodes) {
    const info = describe(el);
    if (!info) continue;
    const idx = out.length;
    el.setAttribute('data-doro-idx', String(idx));
    out.push({idx, ...info});
    handles.push(el);
  }
  return {elements: out, nodes: handles, focused: document.activeElement,
    focus_info: document.activeElement ? describe(document.activeElement) : null};
}"""
)

_SNAPSHOT_JS = "() => (" + _CAPTURE_JS + ")().elements"

_VISIBLE_TEXT_JS = r"""limit => {
  if (!document.body) return '';
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const chunks = [];
  let size = 0;
  while (walker.nextNode() && size < limit) {
    const node = walker.currentNode, el = node.parentElement;
    if (!el || el.closest('input,textarea,select,[contenteditable],script,style,noscript,[hidden],[aria-hidden="true"]') || !el.getClientRects().length) continue;
    if (getComputedStyle(el).visibility !== 'visible') continue;
    const text = node.textContent.replace(/\s+/g, ' ').trim();
    if (text) { chunks.push(text); size += text.length + 1; }
  }
  return chunks.join('\n').slice(0, limit);
}"""


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
    tabs: list[dict] = field(default_factory=list)
    tab_id: int | None = None

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
        self._tabs: dict[int, object] = {}
        self._next_tab_id = 0
        self._targets: dict[int, tuple[object, dict]] = {}
        self._snapshot_page = None
        self._snapshot_url = ""
        self._focused = None
        self._focused_info = None

    def _launch_context(self, channel: str | None):
        kwargs = {
            "user_data_dir": str(self._user_data_dir),
            "headless": self._headless,
            "no_viewport": True,
            "args": [
                "--hide-crash-restore-bubble",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
            ],
        }
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
        self._clear_targets()
        for closer in (
            lambda: self._context and self._context.close(),
            lambda: self._pw and self._pw.stop(),
        ):
            try:
                closer()
            except Exception as exc:
                logger.debug(f"WebSession 關閉時忽略錯誤：{exc}")
        self._pw = self._context = self._page = None
        self._tabs.clear()

    def snapshot(self) -> PageView:
        if not self.is_open:
            return PageView(error=self._closed_error())
        view = self._snapshot_one(self._page, wait_idle=False)
        view.tabs = self.list_tabs()
        view.tab_id = next((tab["id"] for tab in view.tabs if tab["active"]), None)
        return view

    def list_tabs(self) -> list[dict]:
        """Stable IDs belong to Page objects, never to positions in a list."""
        pages = self.open_pages()
        self._tabs = {key: page for key, page in self._tabs.items() if page in pages}
        for page in pages:
            if page not in self._tabs.values():
                self._tabs[self._next_tab_id] = page
                self._next_tab_id += 1
        result = []
        for key, page in self._tabs.items():
            try:
                result.append(
                    {
                        "id": key,
                        "url": page.url,
                        "title": page.title(),
                        "active": page is self._page,
                    }
                )
            except Exception:
                continue  # A user can close a tab during observation.
        return result

    def switch_tab(self, tab_id: int) -> str | None:
        page = self._tabs.get(tab_id)
        if page is None or page not in self.open_pages():
            return "這個分頁已關閉或不在剛才的分頁清單中，請重新觀察。"
        self.use_page(page)
        return None

    def _clear_targets(self) -> None:
        for handle in [*(item[0] for item in self._targets.values()), self._focused]:
            if handle is not None:
                try:
                    handle.dispose()
                except Exception:
                    pass
        self._targets.clear()
        self._focused = None
        self._focused_info = None
        self._snapshot_page = None

    def snapshot_open_pages(self, *, wait_idle: bool = False) -> list[PageView]:
        views: list[PageView] = []
        for page in self.open_pages():
            views.append(self._snapshot_one(page, wait_idle=wait_idle))
        return views

    def _snapshot_one(self, page, *, wait_idle: bool) -> PageView:
        self._clear_targets()
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
                if url == "about:blank":
                    self._snapshot_page, self._snapshot_url = page, url
                    return PageView(url=url)
                title = (page.title() or "").strip()
                body_text = page.evaluate(_VISIBLE_TEXT_JS, self._max_chars)
                try:
                    # Capture metadata and node identities atomically. Looking
                    # up a CSS index afterwards could bind a replacement node.
                    capture = page.evaluate_handle(_CAPTURE_JS)
                    metadata = capture.get_property("elements")
                    nodes = capture.get_property("nodes")
                    focus_info = capture.get_property("focus_info")
                    try:
                        elements = metadata.json_value()
                        self._focused = capture.get_property("focused")
                        self._focused_info = focus_info.json_value()
                        handles = nodes.get_properties()
                        for element in elements:
                            handle = handles[str(element["idx"])].as_element()
                            if handle is not None:
                                self._targets[element["idx"]] = (handle, element)
                    finally:
                        metadata.dispose()
                        nodes.dispose()
                        focus_info.dispose()
                        capture.dispose()
                except Exception:
                    self._clear_targets()
                    elements = []
                self._snapshot_page, self._snapshot_url = page, url
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
        return PageView(
            error=self._error_or_closed(last_exc or RuntimeError("snapshot"), "讀目前頁面")
        )

    def collect_links(self) -> list[dict]:
        if not self.is_open:
            return []
        try:
            return self._page.evaluate(_LINKS_JS) or []
        except Exception as exc:
            logger.debug(f"collect_links 失敗：{exc}")
            return []

    def goto(self, url: str, timeout_ms: int | None = None) -> str | None:
        if not valid_web_url(url):
            return "只接受沒有帳密的完整 http 或 https 網址。"
        return self._guard(
            lambda: self._page.goto(
                url, wait_until="domcontentloaded", timeout=timeout_ms or self._nav_timeout_ms
            ),
            f"打開 {url}",
        )

    def new_tab(self, url: str, timeout_ms: int | None = None) -> str | None:
        if not valid_web_url(url):
            return "只接受沒有帳密的完整 http 或 https 網址。"
        if len(self.open_pages()) >= 12:
            return "操作分頁已達 12 個，請使用現有分頁。"
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
        return self._act_on_target(index, "click")

    def type_index(self, index: int, text: str) -> str | None:
        return self._act_on_target(index, "type", text=text)

    def _act_on_target(
        self, index: int, verb: str, *, text: str = "", checked: bool = False
    ) -> str | None:
        if not self.is_open:
            return self._closed_error()
        item = self._targets.get(index)
        if (
            item is None
            or self._snapshot_page is not self._page
            or self._page.url != self._snapshot_url
        ):
            return "目標或頁面已變動，請重新觀察後再操作。"
        handle, expected = item
        try:
            current = handle.evaluate(_ELEMENT_INFO_JS)
            ignore = {"idx", "focused", "in_viewport"}
            if current is None or any(
                current.get(key) != value for key, value in expected.items() if key not in ignore
            ):
                return "目標已變動，原本的確認不再適用，請重新觀察。"
            if current["disabled"]:
                return "這個元件目前停用，請重新觀察。"
            if verb in {"type", "select", "check"} and current["sensitive"]:
                return "密碼或驗證碼請使用者自行輸入。"
            if verb == "click":
                handle.click(timeout=self._nav_timeout_ms)
            elif verb == "type":
                handle.fill(text, timeout=self._nav_timeout_ms)
            elif verb == "hover":
                handle.hover(timeout=self._nav_timeout_ms)
            elif verb == "select":
                if current["tag"] != "select" or current["multiple"]:
                    return "請選擇單選下拉選單。"
                options = [option for option in current["options"] if option["label"] == text]
                if len(options) != 1 or options[0]["disabled"]:
                    return "選項不唯一、不存在或停用，請重新觀察。"
                handle.select_option(label=text, timeout=self._nav_timeout_ms)
            elif verb == "check":
                if current["tag"] != "input" or current["input_type"] not in {"checkbox", "radio"}:
                    return "這不是原生勾選框或單選按鈕。"
                if current["input_type"] == "radio" and not checked:
                    return "單選按鈕請改選另一個選項，不能直接取消。"
                handle.set_checked(checked, timeout=self._nav_timeout_ms)
            return None
        except Exception:
            # Playwright call logs can contain filled text. Never forward them.
            logger.warning("目標操作失敗（不記錄輸入或選項內容）")
            return "目標操作失敗，請重新觀察頁面後再試。"

    def press(self, key: str) -> str | None:
        try:
            if self._focused is None or not self._focused.evaluate(
                "el => el.isConnected && el === document.activeElement"
            ):
                return "鍵盤焦點已變動，請重新觀察。"
            current = self._focused.evaluate(_ELEMENT_INFO_JS)
            if current != self._focused_info:
                return "鍵盤目標已變動，請重新觀察。"
        except Exception:
            return "鍵盤焦點已變動，請重新觀察。"
        return self._guard(lambda: self._page.keyboard.press(key), f"按下 {key}")

    def scroll(self, direction: str) -> str | None:
        dy = 600 if direction.strip().lower() != "up" else -600
        return self._guard(lambda: self._page.mouse.wheel(0, dy), f"捲動 {direction}")

    def back(self) -> str | None:
        return self._guard(lambda: self._page.go_back(), "回上一頁")

    def execute(self, action: WebAction) -> str | None:
        # Validate again at the executor boundary, including non-model callers.
        try:
            params = dict(action.params)
            for key in ("n", "tab_id"):
                if key in params:
                    params[key] = int(params[key])
            if "checked" in params:
                if str(params["checked"]).lower() not in {"true", "false"}:
                    return "勾選狀態必須是 true 或 false。"
                params["checked"] = str(params["checked"]).lower() == "true"
            WebStep(action=action.verb, line="完成", **params)
        except (ValueError, TypeError):
            return "操作參數不合格，請重新決定下一步。"
        verb = action.verb
        if verb not in {"goto", "new_tab", "switch_tab", "done"}:
            if not self.is_open:
                return self._closed_error()
            if self._snapshot_page is not self._page or self._page.url != self._snapshot_url:
                return "頁面已變動，請重新觀察後再操作。"
        if verb in TARGET_VERBS:
            return self._act_on_target(
                action.index(),
                verb,
                text=params.get("text", ""),
                checked=params.get("checked", False),
            )
        if verb == "new_tab":
            return self.new_tab(params["url"])
        if verb == "switch_tab":
            return self.switch_tab(params["tab_id"])
        if verb == "wait":
            return self._guard(
                lambda: self._page.wait_for_timeout(float(params["seconds"]) * 1000), "等候頁面"
            )
        if verb == "goto":
            return self.goto(action.params.get("url", ""))
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
