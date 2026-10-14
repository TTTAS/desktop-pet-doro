"""Keep Doro's always-on-top windows above ordinary windows on Windows.

What the exit-diagnostics logs showed: Doro's WS_EX_TOPMOST flag stays set, yet
modern apps (the Photos app) end up *above* it while opening or closing —
an ordinary window (topmost=False, band 1) stacked over a topmost one, which
Windows normally never allows. It happens during their cloak/uncloak
animations; Doro cannot prevent it, only undo it quickly.

The guard re-raises a Doro window when, and only when, a visible ordinary
window of another program in the normal desktop band overlaps it from above:
- Windows event hooks (foreground change, window shown, window uncloaked)
  trigger a check at once and again shortly after, when animations finish;
- a 0.5 s poll is the safety net;
- topmost windows of other apps and higher system bands (Alt+Tab is band 16,
  Start menu, taskbar overlays) are left alone: no fighting, no logging;
- if Windows ever clears Doro's topmost flag, it is restored and logged.
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
_ZBID_DESKTOP = 1  # the band ordinary app windows live in
_EVENT_SYSTEM_FOREGROUND = 0x0003
_EVENT_OBJECT_SHOW = 0x8002
_EVENT_OBJECT_CLOAKED = 0x8017
_EVENT_OBJECT_UNCLOAKED = 0x8018
_WINEVENT_OUTOFCONTEXT = 0x0000
_WINEVENT_SKIPOWNPROCESS = 0x0002

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
        user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
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
    """Describe an ordinary window of another program stacked above ``hwnd`` and overlapping it.

    Only visible, uncloaked, non-topmost windows in the normal desktop band count:
    those are the ones that should never be above a topmost window.
    """
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
            band = wintypes.DWORD(_ZBID_DESKTOP)
            if get_band is not None:
                get_band(above, ctypes.byref(band))
            ordinary = not _win_is_topmost(above) and band.value <= _ZBID_DESKTOP
            if pid.value != own_pid and not cloaked.value and overlaps and ordinary:
                length = user32.GetWindowTextLengthW(above)
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(above, title, length + 1)
                return f"{title.value or 'untitled'!r} (hwnd {int(above):#x}, pid {pid.value})"
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
        settle_ms: int = 150,
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
        # Coalesces bursts of window events into one check on the next loop turn.
        self._soon = QtCore.QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(0)
        self._soon.timeout.connect(self.check)
        self._settled = QtCore.QTimer(self)
        self._settled.setSingleShot(True)
        self._settled.setInterval(settle_ms)
        self._settled.timeout.connect(self.check)
        self._hooks: list[int] = []
        self._hook_proc = None

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._soon.stop()
        self._settled.stop()

    def on_window_event(self) -> None:
        """Another window changed: check now, and again once its animation settles."""
        self._soon.start()
        self._settled.start()

    def install_window_event_hooks(self) -> None:
        """Windows only: call on_window_event for foreground / show / (un)cloak events."""
        ctypes, wintypes, user32, _, _ = _win32()
        proc_type = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        def proc(_hook, event, _hwnd, id_object, id_child, _thread, _time):
            if event == _EVENT_SYSTEM_FOREGROUND or (id_object == 0 and id_child == 0):
                self.on_window_event()

        self._hook_proc = proc_type(proc)  # must outlive the hooks
        flags = _WINEVENT_OUTOFCONTEXT | _WINEVENT_SKIPOWNPROCESS
        for first, last in (
            (_EVENT_SYSTEM_FOREGROUND, _EVENT_SYSTEM_FOREGROUND),
            (_EVENT_OBJECT_SHOW, _EVENT_OBJECT_SHOW),
            (_EVENT_OBJECT_CLOAKED, _EVENT_OBJECT_UNCLOAKED),
        ):
            hook = user32.SetWinEventHook(first, last, None, self._hook_proc, 0, 0, flags)
            if hook:
                self._hooks.append(hook)

    def remove_window_event_hooks(self) -> None:
        if not self._hooks:
            return
        _, _, user32, _, _ = _win32()
        for hook in self._hooks:
            user32.UnhookWinEvent(hook)
        self._hooks.clear()

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
    try:
        guard.install_window_event_hooks()
    except Exception as exc:  # pragma: no cover - polling still works without hooks
        guard._log(f"window event hooks unavailable, polling only ({exc})")
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(guard.remove_window_event_hooks)
    guard.start()
    return guard
