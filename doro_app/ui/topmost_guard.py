"""Keep Doro's always-on-top windows on top on Windows.

Reported on Windows: other apps' windows (the Photos app in particular) could
cover Doro even though Doro's WS_EX_TOPMOST flag stayed set the whole time
(confirmed by exit-diagnostics logs), and after closing Photos Doro was left
behind File Explorer until Win+D revealed it.

The guard checks twice a second, for every visible window that asked for
Qt.WindowStaysOnTopHint:
- if Windows cleared its topmost flag, restore it and log;
- if a visible window of another program sits above it and overlaps it, raise
  it again. The covering window is logged once, with its topmost flag and z-band,
  so a window that cannot be beaten (a higher band) shows up in the log.
Doro's own windows (menus, dialogs) are never treated as covering.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from PySide6 import QtCore, QtWidgets

_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_GW_HWNDPREV = 3
_DWMWA_CLOAKED = 14

_api = None


def _win32():
    """user32 / dwmapi with explicit signatures.

    Without them ctypes passes ints as 32-bit C ints, so HWND_TOPMOST (-1) is not
    guaranteed to reach SetWindowPos as a pointer-sized -1 on 64-bit Windows.
    """
    global _api
    if _api is None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = wintypes.LONG
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        get_band = getattr(user32, "GetWindowBand", None)  # undocumented, Windows 8+
        if get_band is not None:
            get_band.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        _api = (ctypes, wintypes, user32, dwmapi, get_band)
    return _api


def _win_is_topmost(hwnd: int) -> bool:
    _, _, user32, _, _ = _win32()
    return bool(user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST)


def _win_covered_by(hwnd: int) -> str | None:
    """Describe another process's visible window above ``hwnd`` that overlaps it."""
    ctypes, wintypes, user32, dwmapi, get_band = _win32()
    own_pid = os.getpid()
    mine = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(mine))
    above = user32.GetWindow(hwnd, _GW_HWNDPREV)
    while above:
        if user32.IsWindowVisible(above):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(above, ctypes.byref(pid))
            cloaked = wintypes.DWORD()
            dwmapi.DwmGetWindowAttribute(
                above, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            rect = wintypes.RECT()
            user32.GetWindowRect(above, ctypes.byref(rect))
            overlaps = (
                rect.left < mine.right
                and mine.left < rect.right
                and rect.top < mine.bottom
                and mine.top < rect.bottom
            )
            if pid.value != own_pid and not cloaked.value and overlaps:
                length = user32.GetWindowTextLengthW(above)
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(above, title, length + 1)
                band = wintypes.DWORD()
                if get_band is not None:
                    get_band(above, ctypes.byref(band))
                return (
                    f"{title.value or 'untitled'!r} (hwnd {int(above):#x}, pid {pid.value}, "
                    f"topmost={_win_is_topmost(above)}, band={band.value})"
                )
        above = user32.GetWindow(above, _GW_HWNDPREV)
    return None


def _win_make_topmost(hwnd: int) -> None:
    _, _, user32, _, _ = _win32()
    user32.SetWindowPos(
        hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
    )


class TopmostGuard(QtCore.QObject):
    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        *,
        is_topmost: Callable[[int], bool] = _win_is_topmost,
        make_topmost: Callable[[int], None] = _win_make_topmost,
        covered_by: Callable[[int], str | None] = _win_covered_by,
        log: Callable[[str], None] | None = None,
        interval_ms: int = 500,
    ) -> None:
        super().__init__(parent)
        self._is_topmost = is_topmost
        self._make_topmost = make_topmost
        self._covered_by = covered_by
        self._last_cover: dict[int, str] = {}  # log each covering window once
        self._log = log or (lambda message: print(f"[topmost] {message}", flush=True))
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def check(self) -> int:
        """Keep windows on top; returns how many windows had to be raised."""
        fixed = 0
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not widget.isVisible():
                continue
            if not widget.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint:
                continue
            hwnd = int(widget.winId())
            if not hwnd:
                continue
            name = type(widget).__name__
            if not self._is_topmost(hwnd):
                self._log(f"{name} lost always-on-top; restoring it")
            else:
                cover = self._covered_by(hwnd)
                if cover is None:
                    self._last_cover.pop(hwnd, None)
                    continue
                if self._last_cover.get(hwnd) != cover:
                    self._log(f"{name} was covered by {cover}; raising it again")
                    self._last_cover[hwnd] = cover
            self._make_topmost(hwnd)
            fixed += 1
        return fixed


def install(
    parent: QtCore.QObject, log: Callable[[str], None] | None = None
) -> TopmostGuard | None:
    if sys.platform != "win32":
        return None
    guard = TopmostGuard(parent, log=log)
    guard.start()
    return guard
