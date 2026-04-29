"""Idle behavior manager - triggers autonomous actions when the user is away."""

from __future__ import annotations

import random
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6 import QtCore

from ..constants import IDLE_BEHAVIOR_MIN_INTERVAL, IDLE_BEHAVIOR_MAX_INTERVAL
from ..utils.actions import MOVE_DIRECTIONS
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .chat.orchestrator import ChatOrchestrator
    from .movement.manager import MovementManager
    from .state import StateService

logger = get_logger(__name__)

_DIRECTIONS = list(set(MOVE_DIRECTIONS.values()))


class IdleActionType(Enum):
    SPEAK = auto()
    MOVE = auto()
    TRANSITION = auto()


_IDLE_ACTIONS = list(IdleActionType)


class IdleBehaviorManager(QtCore.QObject):
    """Triggers random autonomous actions (speak / move / transition) at idle intervals."""

    action_triggered = QtCore.Signal(str)

    def __init__(
        self,
        *,
        companion_file: Path,
        chat_orchestrator: ChatOrchestrator,
        movement_manager: MovementManager,
        state_service: StateService,
        idle_seconds_provider: Callable[[], float],
        mark_activity: Callable[[], None],
    ):
        super().__init__()
        self._chat_orchestrator = chat_orchestrator
        self._movement = movement_manager
        self._state_service = state_service
        self._idle_seconds = idle_seconds_provider
        self._mark_activity = mark_activity

        self._lines: list[str] = []
        self._load_lines(companion_file)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._schedule_next()

    def _load_lines(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
            self._lines = [l.strip() for l in raw.splitlines() if l.strip()]
            logger.debug("Loaded %d companion lines", len(self._lines))
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Failed to load companion lines: %s", e)

    def _schedule_next(self) -> None:
        delay = random.uniform(IDLE_BEHAVIOR_MIN_INTERVAL, IDLE_BEHAVIOR_MAX_INTERVAL)
        self._timer.start(int(delay * 1000))

    def reset(self) -> None:
        """Reset the idle timer (call on user interaction)."""
        self._schedule_next()

    def _on_timer(self) -> None:
        idle = self._idle_seconds()
        if idle < IDLE_BEHAVIOR_MIN_INTERVAL:
            self._schedule_next()
            return

        if self._chat_orchestrator.is_inflight:
            self._schedule_next()
            return

        if self._movement.has_active_movement:
            self._schedule_next()
            return

        action = random.choice(_IDLE_ACTIONS)
        logger.debug("Idle action: %s", action.name)

        if action is IdleActionType.SPEAK:
            self._do_speak()
        elif action is IdleActionType.MOVE:
            self._do_move()
        elif action is IdleActionType.TRANSITION:
            self._do_transition()

        self._mark_activity()
        self._schedule_next()

    def _do_speak(self) -> None:
        if not self._lines:
            self._do_move()
            return
        line = random.choice(self._lines)
        self._chat_orchestrator.send_message(line, silent=True, is_auto=True)
        self.action_triggered.emit(f"speak: {line}")

    def _do_move(self) -> None:
        direction = random.choice(_DIRECTIONS)
        report = self._movement.apply_directional_move(direction)
        self.action_triggered.emit(f"move: {report}")

    def _do_transition(self) -> None:
        keys = [
            k for k in self._state_service.visible_state_keys()
            if not self._state_service.is_movement_only_state(k)
            and k != self._state_service.get_current_state_key()
        ]
        if not keys:
            self._do_move()
            return
        target = random.choice(keys)
        self._state_service.set_state(target)
        self.action_triggered.emit(f"transition: {target}")
