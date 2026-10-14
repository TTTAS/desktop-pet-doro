"""Keep Doro's always-on-top windows on top on Windows.

Reported on Windows: after closing the Photos app, Doro kept running (it still
moved and logged) but could no longer be seen, with no close or hide event —
it had dropped behind other windows. Windows can clear a window's topmost
state (WS_EX_TOPMOST) when another app's windows are torn down; Qt is not told,
so the window stays "shown" yet hidden behind File Explorer.

The guard checks once a second and restores topmost for every visible window
that asked for Qt.WindowStaysOnTopHint, logging each time it had to.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6 import QtCore, QtWidgets

_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010


def _win_is_topmost(hwnd: int) -> bool:
    import ctypes

    return bool(ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST)


def _win_make_topmost(hwnd: int) -> None:
    import ctypes

    ctypes.windll.user32.SetWindowPos(
        hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
    )


class TopmostGuard(QtCore.QObject):
    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        *,
        is_topmost: Callable[[int], bool] = _win_is_topmost,
        make_topmost: Callable[[int], None] = _win_make_topmost,
        log: Callable[[str], None] | None = None,
        interval_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self._is_topmost = is_topmost
        self._make_topmost = make_topmost
        self._log = log or (lambda message: print(f"[topmost] {message}", flush=True))
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def check(self) -> int:
        """Restore topmost where it was lost; returns how many windows were fixed."""
        fixed = 0
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not widget.isVisible():
                continue
            if not widget.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint:
                continue
            hwnd = int(widget.winId())
            if not hwnd or self._is_topmost(hwnd):
                continue
            self._log(f"{type(widget).__name__} lost always-on-top; restoring it")
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
