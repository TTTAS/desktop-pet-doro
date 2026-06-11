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
    d = None
    try:
        d = display.Display()
        root = d.screen().root
        # Walk down the X tree by *coordinate*, not by the user's cursor.
        # The pre-rewrite version used `query_pointer()` (the window the
        # mouse currently sits over) and threw away the (x, y) it was
        # asked to inspect — meaning the allowlist sampled a different
        # window from the click target. `translate_coords(root, x, y)`
        # returns the immediate child of `win` containing (x, y), or
        # X.NONE when `win` itself is the deepest container.
        win = root
        while True:
            res = win.translate_coords(root, int(x), int(y))
            child = getattr(res, "child", None)
            if not child or child == X.NONE:
                break
            win = child
        # WM_CLASS lives on the client top-level, which may sit above the
        # deepest hit (decorations, subwindows). Climb until we find it
        # or hit the root.
        while win is not None and win != root:
            wm_class = win.get_wm_class()
            if wm_class and len(wm_class) >= 2:
                return wm_class[1]
            try:
                win = win.query_tree().parent
            except Exception:
                return None
        return None
    except Exception:
        return None
    finally:
        if d is not None:
            try:
                d.close()
            except Exception:
                pass


def _resolve_hwnd_at_win32(x: int, y: int):  # pragma: no cover - needs Windows
    """Walk the desktop z-order to find the top-level hwnd at (x, y).

    Skips invisible, disabled, and transparent windows so Doro itself
    and Win11's Snap Layouts overlay don't shadow the real target.
    Returns the raw ctypes HWND (or None) plus the bound `user32`
    handle so callers can do follow-up calls without re-binding
    argtypes.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None, None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        # Bind argtypes/restype for the calls that take or return HWND.
        # On 64-bit Windows HWND is pointer-sized; without explicit types
        # ctypes treats them as `int` and truncates. POINT must be
        # declared so it's passed by value correctly.
        user32.GetDesktopWindow.restype = wintypes.HWND
        user32.ChildWindowFromPointEx.argtypes = [
            wintypes.HWND, wintypes.POINT, wintypes.UINT,
        ]
        user32.ChildWindowFromPointEx.restype = wintypes.HWND
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetClassNameW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int

        CWP_SKIPINVISIBLE = 0x0001
        CWP_SKIPDISABLED = 0x0002
        CWP_SKIPTRANSPARENT = 0x0004

        pt = wintypes.POINT(int(x), int(y))
        flags = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
        desktop = user32.GetDesktopWindow()
        hwnd = user32.ChildWindowFromPointEx(desktop, pt, flags)
        if not hwnd:
            hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return None, user32
        return hwnd, user32
    except Exception:
        return None, None


def _read_window_class_win32(x: int, y: int) -> Optional[str]:  # pragma: no cover - needs Windows
    hwnd, user32 = _resolve_hwnd_at_win32(x, y)
    if not hwnd or user32 is None:
        return None
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or None
    except Exception:
        return None


def _read_handle_at_win32(x: int, y: int) -> Optional[int]:  # pragma: no cover - needs Windows
    hwnd, _ = _resolve_hwnd_at_win32(x, y)
    if not hwnd:
        return None
    try:
        return int(hwnd)
    except Exception:
        return None
    except Exception:
        return None


def _read_window_class_macos(x: int, y: int) -> Optional[str]:  # pragma: no cover - not on dev target
    # Out of scope for Phase 1c — return None so the allowlist check refuses.
    return None


def read_handle_at(x: int, y: int) -> Optional[int]:
    """Return the OS top-level window handle at physical (x, y), or None.

    Same z-order walk as :func:`read_at`; returns the hwnd integer so
    callers can compare it with :func:`read_foreground_window_handle`
    to refuse clicks on background windows (a stronger gate than the
    class allowlist alone).
    """
    if sys.platform == "win32":
        return _read_handle_at_win32(int(x), int(y))
    # X11/macOS: no implementation yet — caller treats None as
    # "can't check foreground" and skips the gate.
    return None


def read_foreground_window_handle() -> Optional[int]:
    """Return the OS handle of the focused (foreground) window, or None.

    Phase 1d: the a11y backend needs a handle to anchor its subtree read.
    Windows is implemented; other platforms return None (no tree is read,
    which the A11yService treats as "nothing to show").
    """
    if sys.platform == "win32":
        return _get_foreground_window_handle_win32()
    # X11 / macOS / Wayland: deferred to a later phase.
    return None


def pid_for_handle(handle: int) -> Optional[int]:
    """Return the process id that owns ``handle``, or None.

    Used by the foreground tracker to skip Doro's own windows when remembering
    "the last external window the user looked at". Windows is implemented;
    other platforms return None.
    """
    if sys.platform == "win32":
        return _pid_for_handle_win32(handle)
    return None


def window_class_for_handle(handle: int) -> Optional[str]:
    """Return the class string of the window identified by ``handle``, or None.

    Used to gate a11y reads against the sensitive-app blacklist without a
    pixel coordinate. Reads only the class — never title, content, or pixels.
    """
    if sys.platform == "win32":
        return _window_class_for_handle_win32(handle)
    return None


def _get_foreground_window_handle_win32() -> Optional[int]:  # pragma: no cover - needs Windows
    try:
        import ctypes
    except ImportError:
        return None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def _pid_for_handle_win32(handle: int) -> Optional[int]:  # pragma: no cover - needs Windows
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(int(handle), ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def _window_class_for_handle_win32(handle: int) -> Optional[str]:  # pragma: no cover - needs Windows
    try:
        import ctypes
    except ImportError:
        return None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(int(handle), buf, 256)
        return buf.value or None
    except Exception:
        return None
