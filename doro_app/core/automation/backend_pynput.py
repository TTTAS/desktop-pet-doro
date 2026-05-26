"""Real input backend, layered over pynput.

Only `pynput.mouse` (for synthesizing a single left click) and
`pynput.keyboard.Listener` (for the Esc kill-switch) are touched.

The Listener is filtered to Esc on the very first line of its callback;
this is by design and is part of the privacy contract documented in the
plan. No other key data is logged, stored, or forwarded.

Foreground-window class lookup is platform-specific (Xlib on X11, ctypes
on Windows). Both fall back to None on error; AutomationManager treats a
missing class as "not in allowlist" and refuses to fire.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from ...utils.logger import get_logger

logger = get_logger("doro.automation.backend")


class PynputBackend:
    """`InputBackendPort` implementation backed by pynput + platform APIs."""

    def __init__(self) -> None:
        # Defer the pynput import so importing this module on a system
        # without pynput doesn't break (Doro can run without automation).
        try:
            from pynput import mouse as _mouse
            from pynput import keyboard as _keyboard
        except ImportError as exc:  # pragma: no cover - install-time path
            raise RuntimeError(
                "pynput is required for automation; install with: pip install pynput"
            ) from exc

        self._mouse_controller = _mouse.Controller()
        self._Button = _mouse.Button
        self._Key = _keyboard.Key
        self._Listener = _keyboard.Listener

        self._listener: Optional[_keyboard.Listener] = None
        self._left_pressed = False
        self._mouse_listener: Optional[_mouse.Listener] = None
        self._install_mouse_state_listener(_mouse)

    # ------------------------------------------------------------------ InputBackendPort

    def click_left(self, x: int, y: int) -> None:
        self._mouse_controller.position = (int(x), int(y))
        self._mouse_controller.click(self._Button.left, 1)

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        if sys.platform.startswith("linux"):
            return _read_window_class_x11(int(x), int(y))
        if sys.platform == "win32":
            return _read_window_class_win32(int(x), int(y))
        if sys.platform == "darwin":  # pragma: no cover - not the dev target
            return _read_window_class_macos(int(x), int(y))
        return None

    def is_left_button_pressed(self) -> bool:
        return self._left_pressed

    def install_esc_listener(self, on_esc: Callable[[], None]) -> None:
        Key = self._Key

        def _on_press(key) -> None:
            # ─── Privacy contract ─────────────────────────────────────────
            # First line: reject every non-Esc key. We do NOT log, store,
            # forward, or branch on any other key's identity. Unit tests in
            # tests/core/automation/test_backend_listener.py guard this.
            if key != Key.esc:
                return
            try:
                on_esc()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Esc callback raised")

        self._listener = self._Listener(on_press=_on_press)
        self._listener.daemon = True
        self._listener.start()

    def shutdown(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._listener = None
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._mouse_listener = None

    # ------------------------------------------------------------------ Internals

    def _install_mouse_state_listener(self, mouse_module) -> None:
        """Track the left-button state by listening to mouse events.

        pynput.mouse has no "is currently pressed" query; we maintain a
        flag from the on_click stream instead.
        """

        def _on_click(_x, _y, button, pressed) -> None:
            if button == self._Button.left:
                self._left_pressed = bool(pressed)

        try:
            self._mouse_listener = mouse_module.Listener(on_click=_on_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
        except Exception:  # pragma: no cover - some platforms restrict listeners
            logger.warning("Mouse state listener unavailable; drag-grace will be best-effort")
            self._mouse_listener = None


# ────────────────────────────────────────────────────────────────────────
# Platform-specific window-class readers. Each only reads the class string
# (NOT the title, NOT the contents) and returns None on any error.
# ────────────────────────────────────────────────────────────────────────


def _read_window_class_x11(x: int, y: int) -> Optional[str]:  # pragma: no cover - needs X server
    try:
        from Xlib import display, X  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        d = display.Display()
        root = d.screen().root
        # Find the topmost child window at (x, y).
        target = root
        while True:
            data = target.query_pointer()
            child = data.child
            if child == X.NONE or not child:
                break
            target = child
            # Don't loop forever — XQueryPointer with a point we set
            target_data = target.translate_coords(root, x, y)  # noqa: F841
        wm_class = target.get_wm_class()
        return wm_class[1] if wm_class and len(wm_class) >= 2 else None
    except Exception:
        return None


def _read_window_class_win32(x: int, y: int) -> Optional[str]:  # pragma: no cover - needs Windows
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        pt = wintypes.POINT(int(x), int(y))
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return None
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or None
    except Exception:
        return None


def _read_window_class_macos(x: int, y: int) -> Optional[str]:  # pragma: no cover - not on dev target
    # Out of scope for Phase 1c — return None so the allowlist check refuses.
    return None
