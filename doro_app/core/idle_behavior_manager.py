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
    from .action import ActionDispatcher
    from .action.phases import ScheduleFn
    from .chat.orchestrator import ChatOrchestrator
    from .movement.manager import MovementManager
    from .state import StateService

logger = get_logger(__name__)

_DIRECTIONS = list(set(MOVE_DIRECTIONS.values()))


class IdleActionType(Enum):
    SPEAK = auto()
    MOVE = auto()
    TRANSITION = auto()
    WALK_AND_SPEAK = auto()


_IDLE_ACTIONS = list(IdleActionType)

# How far each idle walk travels, in px. A random distance in this range is
# picked per walk so the wandering varies instead of always the same hop.
# Bump these to make Doro roam farther each time.
IDLE_WALK_MIN_DISTANCE = 240.0
IDLE_WALK_MAX_DISTANCE = 560.0


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
    ):
        super().__init__()
        self._chat_orchestrator = chat_orchestrator
        self._movement = movement_manager
        self._state_service = state_service
        self._idle_seconds = idle_seconds_provider
        self._mark_activity = mark_activity
        self._action_dispatcher = action_dispatcher
        self._schedule = schedule

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
        # No user-activity gate: Doro acts on her own 1-3 min rhythm whether
        # or not you're using the computer. The checks below only defer when
        # *Doro herself* is busy (mid-request / mid-move / mid-transition).
        if self._chat_orchestrator.is_inflight:
            self._schedule_next()
            return

        # 讀 / 操作網頁進行中也要安靜：不要在操作時插話、亂走，以免跟操作搶焦點
        # 或干擾（隔離規則 Q2）。用 getattr 兼容沒有這個屬性的舊/假替身。
        if getattr(self._chat_orchestrator, "is_web_busy", False):
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
        elif action is IdleActionType.WALK_AND_SPEAK:
            self._do_walk_and_speak()

        self._mark_activity()
        self._schedule_next()

    def _do_speak(self) -> None:
        # No API: the companion lines are already finished dialogue, so we
        # show one directly instead of round-tripping it through the LLM.
        if not self._lines:
            self._do_move()
            return
        line = random.choice(self._lines)
        self._chat_orchestrator.speak_line(line)

    def _do_walk_and_speak(self) -> None:
        # Walk somewhere, then say a line once she arrives. Falls back to a
        # plain move when there's nothing to say.
        if not self._lines:
            self._do_move()
            return
        line = random.choice(self._lines)
        direction = random.choice(_DIRECTIONS)
        distance = random.uniform(IDLE_WALK_MIN_DISTANCE, IDLE_WALK_MAX_DISTANCE)
        if self._action_dispatcher is not None and self._schedule is not None:
            from .action import make_walk_and_speak_action
            self._action_dispatcher.dispatch(
                make_walk_and_speak_action(
                    self._movement,
                    self._schedule,
                    direction=direction,
                    distance=distance,
                    speak=lambda: self._chat_orchestrator.speak_line(line),
                )
            )
        else:
            # Legacy / unit-test path with no dispatcher: kick off the walk,
            # then speak. (Without the dispatcher there's no completion wait,
            # so the strict "arrive first" ordering only holds on the
            # dispatcher path above — which is what production uses.)
            self._movement.apply_directional_walk(direction, distance)
            self._chat_orchestrator.speak_line(line)

    def _do_move(self) -> None:
        # Animated wander (a visible walk), not the instant one-step hop —
        # idle movement only makes sense if you can see it happen.
        direction = random.choice(_DIRECTIONS)
        distance = random.uniform(IDLE_WALK_MIN_DISTANCE, IDLE_WALK_MAX_DISTANCE)
        if self._action_dispatcher is not None and self._schedule is not None:
            from .action import make_walk_and_speak_action
            self._action_dispatcher.dispatch(
                make_walk_and_speak_action(
                    self._movement, self._schedule, direction=direction, distance=distance
                )
            )
        else:
            self._movement.apply_directional_walk(direction, distance)

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
