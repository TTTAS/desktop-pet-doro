"""Platform-specific foreground-window class reader.

No pynput dependency: this module is safe to import even on systems
without the optional `automation` extra installed. Hot path consumers:

- ``PynputBackend.read_window_class_at`` (allowlist gating).
- ``DoroApp._build_doro_state_text`` (LLM context injection — Phase 1c hotfix).

Each platform helper reads only the **class string** of the window at the
given physical pixel — never the title, never the contents. Returns
``None`` on any error so callers can treat unreadable windows as "not
in allowlist".
"""

from __future__ import annotations

import sys
from typing import Optional


def read_at(x: int, y: int) -> Optional[str]:
    """Return the class string of the window under physical pixel (x, y), or None."""
    if sys.platform.startswith("linux"):
        return _read_window_class_x11(int(x), int(y))
    if sys.platform == "win32":
        return _read_window_class_win32(int(x), int(y))
    if sys.platform == "darwin":
        return _read_window_class_macos(int(x), int(y))
    return None


def _read_window_class_x11(x: int, y: int) -> Optional[str]:  # pragma: no cover - needs X server
    try:
        from Xlib import display, X  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        d = display.Display()
        root = d.screen().root
        target = root
        while True:
            data = target.query_pointer()
            child = data.child
            if child == X.NONE or not child:
                break
            target = child
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
