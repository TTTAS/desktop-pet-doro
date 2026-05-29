"""A11yService — gated reader of the foreground window's element tree.

Pipeline for each call to :meth:`read_foreground_tree`::

    enabled? ──no──▶ ""
       │ yes
    foreground handle ──none──▶ ""
       │
    window class ──blacklisted / session-blacklisted──▶ ""
       │
    backend.read_elements (timeout) ──timeout/none──▶ "" (3 timeouts ⇒ blacklist class)
       │
    filter + redact ──empty──▶ ""
       │
    serialize (≤4KB) ──▶ "[前景視窗元件樹]\n…"

The read is wrapped in a thread with a hard timeout because UIA/AT-SPI can
hang on some app states; a class that times out repeatedly is added to a
session-local blacklist so chat never stalls on it. Every successful read
is recorded to a local-only audit log (never uploaded).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Callable, Optional

from .filters import filter_elements, is_blacklisted
from .port import A11yBackendPort
from .serializer import serialize
from ..automation import window_class
from ...constants import (
    A11Y_PREVIEW_TIMEOUT_SECONDS,
    A11Y_READ_TIMEOUT_SECONDS,
    A11Y_TIMEOUT_BLACKLIST_THRESHOLD,
)
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger

logger = get_logger("doro.a11y")

HandleProvider = Callable[[], Optional[int]]
ClassProvider = Callable[[int], Optional[str]]

_TREE_HEADER = "[前景視窗元件樹]"
_AUDIT_PATH = Path.home() / ".doro" / "share_audit.log"


class A11yService:
    """Compose the foreground-window element block for prompt injection."""

    def __init__(
        self,
        *,
        config_manager: ConfigManager,
        backend: A11yBackendPort,
        handle_provider: HandleProvider | None = None,
        class_provider: ClassProvider | None = None,
        audit_path: Path | None = None,
    ) -> None:
        self._config = config_manager
        self._backend = backend
        self._handle_provider = handle_provider or window_class.read_foreground_window_handle
        self._class_provider = class_provider or window_class.window_class_for_handle
        self._audit_path = audit_path or _AUDIT_PATH
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="a11y")
        self._session_blacklist: set[str] = set()
        self._timeout_counts: dict[str, int] = {}

    def read_foreground_tree(self) -> str:
        """Return the serialized element block, or "" if nothing to show."""
        if not self._config.automation.a11y_enabled:
            return ""

        handle = self._handle_provider()
        if handle is None:
            return ""

        window_cls = self._class_provider(handle)
        cls_key = (window_cls or "").strip().lower()

        if is_blacklisted(window_cls, self._config.automation.a11y_app_blacklist):
            self._audit(window_cls, 0, blacklisted=True)
            return ""
        if cls_key and cls_key in self._session_blacklist:
            return ""

        elements = self._read_with_timeout(handle, cls_key)
        if elements is None:
            return ""

        # Successful read clears any prior timeout streak for this class.
        self._timeout_counts.pop(cls_key, None)

        filtered = filter_elements(elements)
        if not filtered:
            return ""

        body = serialize(filtered)
        if not body:
            return ""

        self._audit(window_cls, len(body.encode("utf-8")), blacklisted=False)
        return f"{_TREE_HEADER}\n{body}"

    def diagnose_foreground_tree(self) -> tuple[bool, str]:
        """Like :meth:`read_foreground_tree`, but for the settings preview.

        Returns ``(True, serialized_block)`` on success, or ``(False, reason)``
        with a plain-language explanation of why nothing was read. Does not
        write the audit log (this is a diagnostic, not a prompt injection).
        """
        if not self._config.automation.a11y_enabled:
            return False, "a11y 未啟用（請在設定勾選「讓 Doro 讀取前景視窗的可點元素」）"

        handle = self._handle_provider()
        if handle is None:
            return False, "取不到前景視窗（此功能目前僅 Windows 有真實後端）"

        window_cls = self._class_provider(handle)
        cls_key = (window_cls or "").strip().lower()

        if is_blacklisted(window_cls, self._config.automation.a11y_app_blacklist):
            return False, f"此程式（{window_cls}）在隱私黑名單中，已略過"
        if cls_key and cls_key in self._session_blacklist:
            return False, f"此程式（{window_cls}）先前多次逾時，本次 session 已略過"

        elements = self._read_with_timeout(
            handle,
            cls_key,
            timeout=A11Y_PREVIEW_TIMEOUT_SECONDS,
            count_timeout=False,
        )
        if elements is None:
            return False, self._backend_unavailable_reason()

        self._timeout_counts.pop(cls_key, None)
        filtered = filter_elements(elements)
        body = serialize(filtered) if filtered else ""
        if not body:
            visited = getattr(self._backend, "last_visited", 0)
            hint = (
                "前景視窗沒有可互動元件（按鈕／連結／輸入框等）。"
                f"（走訪了 {visited} 個節點）"
            )
            if "chrome" in (window_cls or "").lower():
                hint += (
                    "\nChrome 預設不對外開放網頁內容的無障礙樹；請開網頁無障礙："
                    "網址列輸入 chrome://accessibility 並勾選，或用 "
                    "--force-renderer-accessibility 啟動 Chrome，再試一次。"
                )
            return False, hint

        return True, body

    def _backend_unavailable_reason(self) -> str:
        import sys

        msg = "讀不到元件樹（視窗可能不支援，或讀取逾時）"
        detail = getattr(self._backend, "last_error", None)
        if detail:
            msg += f"\n原因：{detail}"
        if sys.platform == "win32":
            import importlib.util

            if importlib.util.find_spec("uiautomation") is None:
                msg += "；可能未安裝 uiautomation，請執行 pip install \"doro[a11y]\""
        return msg

    def clear_session_blacklist(self) -> None:
        """Forget any window classes skipped after repeated timeouts.

        Lets the user re-enable a11y (or restart) to retry a window that was
        temporarily skipped, without restarting the whole app.
        """
        self._session_blacklist.clear()
        self._timeout_counts.clear()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------ internals

    def _read_with_timeout(
        self,
        handle: int,
        cls_key: str,
        *,
        timeout: float = A11Y_READ_TIMEOUT_SECONDS,
        count_timeout: bool = True,
    ):
        future = self._executor.submit(self._backend.read_elements, handle)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            if not count_timeout:
                return None
            count = self._timeout_counts.get(cls_key, 0) + 1
            self._timeout_counts[cls_key] = count
            if count >= A11Y_TIMEOUT_BLACKLIST_THRESHOLD and cls_key:
                self._session_blacklist.add(cls_key)
                logger.warning(
                    f"a11y read for class {cls_key!r} timed out {count}x; "
                    f"session-blacklisting it"
                )
            return None
        except Exception as exc:
            logger.debug(f"a11y backend read raised: {exc}")
            return None

    def _audit(self, window_cls: str | None, num_bytes: int, *, blacklisted: bool) -> None:
        """Append a local-only audit line. Best-effort; never raises."""
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            status = "BLACKLISTED" if blacklisted else "read"
            with self._audit_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{stamp}\t{status}\tclass={window_cls!r}\tbytes={num_bytes}\n")
        except Exception as exc:  # pragma: no cover - disk/permission edge
            logger.debug(f"a11y audit log write failed: {exc}")
