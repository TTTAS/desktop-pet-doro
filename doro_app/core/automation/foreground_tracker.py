"""Foreground-window tracker that remembers the last *external* window.

Problem it solves: Doro's window activates itself when clicked (no no-activate
flag), so ``GetForegroundWindow()`` returns Doro's own window the moment the
user interacts with Doro — both when pressing the a11y preview and when typing
in the chat box. The a11y reader then sees Doro instead of the app the user
actually cares about.

This tracker polls the foreground window on a timer and keeps the handle of the
most recent window that does **not** belong to Doro's own process. Injected as
the ``handle_provider`` of :class:`A11yService`, it makes both preview and live
chat read "the last window the user was looking at before switching to Doro".

The decision logic is split into the pure :func:`next_external_handle` so it can
be unit-tested without Qt or a real Windows session.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore

from . import window_class


def next_external_handle(
    handle: Optional[int],
    pid: Optional[int],
    own_pid: int,
    previous: Optional[int],
) -> Optional[int]:
    """Return the handle to remember after sampling the foreground window.

    Keeps ``handle`` only when it is a valid window owned by a process other
    than Doro itself; otherwise keeps ``previous`` (so Doro's own window — or an
    unreadable foreground — never overwrites the last external window).
    """
    if handle and pid is not None and pid != own_pid:
        return handle
    return previous


class ForegroundTracker(QtCore.QObject):
    """Polls the foreground window and exposes the last external handle.

    Lightweight: each tick is a single ``GetForegroundWindow`` +
    ``GetWindowThreadProcessId`` call (local, no token cost, no element-tree
    walk). The element tree is only read later, on demand, by the A11yService.
    """

    def __init__(
        self,
        own_pid: int,
        *,
        handle_provider: Callable[[], Optional[int]] = window_class.read_foreground_window_handle,
        pid_provider: Callable[[int], Optional[int]] = window_class.pid_for_handle,
        interval_ms: int = 400,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._own_pid = own_pid
        self._handle_provider = handle_provider
        self._pid_provider = pid_provider
        self._interval_ms = interval_ms
        self._last: Optional[int] = None
        self._timer: QtCore.QTimer | None = None

    def _sample(self) -> None:
        handle = self._handle_provider()
        pid = self._pid_provider(handle) if handle is not None else None
        self._last = next_external_handle(handle, pid, self._own_pid, self._last)

    def handle(self) -> Optional[int]:
        """Return the last remembered external window handle, or None."""
        return self._last

    def start(self) -> None:
        self._sample()
        if self._timer is None:
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._sample)
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
