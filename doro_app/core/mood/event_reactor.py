"""Drives Doro's state-mirror reactions on a timer.

Samples the world every ``EVENT_POLL_INTERVAL_S`` and feeds it to the pure
:class:`EventDetector`; turns the detector's events into free bubble lines.
Also emits :attr:`foreground_app_settled` so the optional screen-read
(proposal 7) can hook the same "you settled into a new app" moment without
re-implementing the settle logic.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Optional

from PySide6 import QtCore

from ...constants import EVENT_POLL_INTERVAL_S
from ...utils.logger import get_logger
from .event_detector import REACTION_LINE_KEYS, EventDetector
from .speech import CompanionLines

logger = get_logger(__name__)


class EventReactor(QtCore.QObject):
    """Timer + providers around a pure :class:`EventDetector`."""

    # Emitted when a new foreground app has settled (class name). Fires
    # regardless of reaction cooldowns — subscribers apply their own gating.
    foreground_app_settled = QtCore.Signal(str)

    def __init__(
        self,
        *,
        foreground_class_provider: Callable[[], Optional[str]],
        idle_seconds_provider: Callable[[], float],
        companion_lines: CompanionLines,
        say_line: Callable[[str], None],
        can_react: Callable[[], bool] | None = None,
        detector: EventDetector | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._foreground_class = foreground_class_provider
        self._idle_seconds = idle_seconds_provider
        self._companion_lines = companion_lines
        self._say_line = say_line
        self._can_react = can_react or (lambda: True)
        self._detector = detector or EventDetector()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(EVENT_POLL_INTERVAL_S * 1000))
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        now = time.time()
        dt = datetime.now()
        try:
            cls = self._foreground_class()
        except Exception:  # provider hits Win32 — never let it kill the timer
            logger.debug("foreground_class provider failed", exc_info=True)
            cls = None
        try:
            idle = float(self._idle_seconds())
        except Exception:
            idle = 0.0

        result = self._detector.poll(
            now=now,
            foreground_class=cls,
            idle_seconds=idle,
            hour=dt.hour,
            date=dt.strftime("%Y-%m-%d"),
        )

        if result.settled_app:
            self.foreground_app_settled.emit(result.settled_app)

        if result.reaction is not None and self._can_react():
            key = REACTION_LINE_KEYS[result.reaction]
            line = self._companion_lines.pick(key)
            if line:
                logger.debug("event reaction %s -> %s", result.reaction.name, line)
                self._say_line(line)
