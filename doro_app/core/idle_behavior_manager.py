"""Idle behavior manager - triggers autonomous actions when the user is away."""

from __future__ import annotations

import random
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6 import QtCore

from ..constants import (
    IDLE_BEHAVIOR_MIN_INTERVAL,
    IDLE_BEHAVIOR_MAX_INTERVAL,
    IDLE_LLM_SPEAK_CHANCE,
)
from ..utils.actions import MOVE_DIRECTIONS
from ..utils.logger import get_logger
from .mood.idle_speech import IdleAction, choose_idle_utterance

if TYPE_CHECKING:
    from .action import ActionDispatcher
    from .action.phases import ScheduleFn
    from .chat.orchestrator import ChatOrchestrator
    from .mood.models import MoodState
    from .mood.speech import CompanionLines
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

    def __init__(
        self,
        *,
        companion_file: Path,
        chat_orchestrator: ChatOrchestrator,
        movement_manager: MovementManager,
        state_service: StateService,
        idle_seconds_provider: Callable[[], float],
        mark_activity: Callable[[], None],
        action_dispatcher: "ActionDispatcher | None" = None,
        schedule: "ScheduleFn | None" = None,
        companion_lines: "CompanionLines | None" = None,
        mood_state_provider: "Callable[[], MoodState] | None" = None,
        say_line: "Callable[[str], None] | None" = None,
    ):
        super().__init__()
        self._chat_orchestrator = chat_orchestrator
        self._movement = movement_manager
        self._state_service = state_service
        self._idle_seconds = idle_seconds_provider
        self._mark_activity = mark_activity
        self._action_dispatcher = action_dispatcher
        self._schedule = schedule
        # Pre-written lines shown straight in the bubble (no LLM). When
        # wired, idle chatter is mostly free; the LLM only improvises
        # occasionally (IDLE_LLM_SPEAK_CHANCE).
        self._companion_lines = companion_lines
        self._mood_state_provider = mood_state_provider
        self._say_line = say_line

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
        except UnicodeDecodeError as e:
            logger.warning("companion.txt is not valid UTF-8: %s", e)
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

        # When the dispatcher is wired, defer idle behavior whenever a
        # user-initiated or LLM-initiated action is in flight. Idle is
        # background fluff — it must not preempt deliberate work.
        if self._action_dispatcher is not None and not self._action_dispatcher.is_idle:
            self._schedule_next()
            return

        if self._state_service.is_transitioning():
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
        # Thin adapter over the tested pure decision (see mood.idle_speech):
        # mostly a free pre-written line straight into the bubble, only
        # occasionally an LLM improv. Gather inputs, then carry out the action.
        canned_line = None
        if self._say_line is not None and self._companion_lines is not None:
            mood = self._mood_state_provider() if self._mood_state_provider else None
            canned_line = self._companion_lines.pick_idle(mood)

        decision = choose_idle_utterance(
            roll=random.random(),
            llm_chance=IDLE_LLM_SPEAK_CHANCE,
            canned_line=canned_line,
            has_llm_seed=bool(self._lines),
        )

        if decision.action is IdleAction.SAY_CANNED and decision.line and self._say_line:
            self._say_line(decision.line)
        elif decision.action is IdleAction.ASK_LLM and self._lines:
            seed = random.choice(self._lines)
            self._chat_orchestrator.send_message(seed, silent=True, is_auto=True)
        else:
            self._do_move()

    def _do_move(self) -> None:
        direction = random.choice(_DIRECTIONS)
        if self._action_dispatcher is not None and self._schedule is not None:
            from .action import make_movement_action
            self._action_dispatcher.dispatch(
                make_movement_action(self._movement, self._schedule, direction=direction)
            )
        else:
            self._movement.apply_directional_move(direction)

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
