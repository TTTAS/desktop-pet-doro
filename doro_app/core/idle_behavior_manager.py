"""Local, interruptible companionship with adjustable activity rhythms."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path

from PySide6 import QtCore

from ..utils.actions import MOVE_DIRECTIONS
from ..utils.logger import get_logger
from .action import Action, make_walk_and_speak_action
from .action.phases import VisualPhase

logger = get_logger(__name__)
_DIRECTIONS = list(set(MOVE_DIRECTIONS.values()))
# Seconds between attempts, followed by logical pixels per walk.
ACTIVITY_PROFILES = {
    "lively": (6, 12, 100, 240),
    "balanced": (40, 75, 50, 130),
    "calm": (90, 150, 30, 80),
}


class IdleActionType(Enum):
    SPEAK = auto()
    MOVE = auto()
    TRANSITION = auto()
    WALK_AND_SPEAK = auto()
    EXPRESSION = auto()


class IdleBehaviorManager(QtCore.QObject):
    """Offer small independent actions, yielding to explicit user interaction."""

    def __init__(
        self,
        *,
        companion_file: Path,
        chat_orchestrator,
        movement_manager,
        state_service,
        idle_seconds_provider: Callable[[], float],
        mark_activity: Callable[[], None],
        action_dispatcher=None,
        schedule=None,
        interaction_busy=None,
        profile_provider=None,
        pose_keys_provider=None,
        quiet_provider=None,
        effects_enabled=None,
        micro_effect=None,
        window=None,
        clock=time.monotonic,
    ):
        super().__init__()
        self._chat_orchestrator = chat_orchestrator
        self._movement = movement_manager
        self._state_service = state_service
        self._idle_seconds = idle_seconds_provider
        self._mark_activity = mark_activity
        self._action_dispatcher = action_dispatcher
        self._schedule = schedule
        self._interaction_busy = interaction_busy or (lambda: False)
        self._profile = profile_provider or (lambda: "lively")
        self._pose_keys = pose_keys_provider or (lambda: ["happy"])
        self._quiet = quiet_provider or (lambda: False)
        self._effects = effects_enabled or (lambda: False)
        self._micro_effect = micro_effect or (lambda _: None)
        self._window = window
        self._clock = clock
        self._last_action = None
        self._resume_pending = False
        self._last_line = None
        self._last_speech = float("-inf")
        self._owned_action = None
        self._owned_movement = None
        self._lines = []
        try:
            self._lines = list(
                dict.fromkeys(
                    line.strip()
                    for line in companion_file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            )
        except (OSError, UnicodeError) as exc:
            logger.debug("Companion lines unavailable: %s", exc)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._schedule_next()

    def _schedule_next(self, *, retry: bool = False) -> None:
        low, high = (
            (45, 90)
            if self._quiet()
            else ACTIVITY_PROFILES.get(self._profile(), ACTIVITY_PROFILES["lively"])[:2]
        )
        if retry and not self._quiet():
            low, high = 2, 3
        self._timer.start(int(random.uniform(low, high) * 1000))

    def reset(self) -> None:
        self._schedule_next()

    def on_mode_changed(self, quiet: bool) -> None:
        """Replace the old mode's timer and resume with a visible local action."""
        self.interrupt()
        self._resume_pending = not quiet
        if not quiet:
            self._timer.start(4000)

    def interrupt(self) -> None:
        """Cancel only our action, preserving any queued deliberate work."""
        dispatcher = self._action_dispatcher
        if (
            dispatcher is not None
            and self._owned_action is not None
            and dispatcher.current is self._owned_action
        ):
            dispatcher.cancel_current("pet-interaction", clear_queue=False)
        self._owned_action = None
        self._owned_movement = None
        self.reset()

    def _on_timer(self) -> None:
        deferred = True
        try:
            if (
                self._interaction_busy()
                or self._idle_seconds() < (8 if self._quiet() else 4)
                or self._chat_orchestrator.is_inflight
                or getattr(self._chat_orchestrator, "is_web_busy", False)
                or self._movement.has_active_movement
                or self._state_service.is_transitioning()
                or (self._action_dispatcher is not None and not self._action_dispatcher.is_idle)
            ):
                return
            deferred = False
            if self._quiet():
                if self._effects():
                    self._micro_effect("stretch")
                return
            choices = [IdleActionType.MOVE, IdleActionType.MOVE]
            if (
                self._eligible_poses()
                and self._action_dispatcher is not None
                and self._schedule is not None
            ):
                choices.append(IdleActionType.TRANSITION)
            if self._effects():
                choices.append(IdleActionType.EXPRESSION)
            if self._lines and self._clock() - self._last_speech >= 90:
                choices.extend([IdleActionType.SPEAK, IdleActionType.WALK_AND_SPEAK])
            choices = [a for a in choices if a != self._last_action] or choices
            action = IdleActionType.MOVE if self._resume_pending else random.choice(choices)
            self._resume_pending = False
            self._last_action = action
            {
                IdleActionType.MOVE: self._do_move,
                IdleActionType.TRANSITION: self._do_transition,
                IdleActionType.SPEAK: self._do_speak,
                IdleActionType.WALK_AND_SPEAK: self._do_walk_and_speak,
                IdleActionType.EXPRESSION: self._do_expression,
            }[action]()
            self._mark_activity()
        finally:
            self._schedule_next(retry=deferred)

    def _line(self) -> str | None:
        choices = [line for line in self._lines if line != self._last_line] or self._lines
        return random.choice(choices) if choices else None

    def _say(self, line: str) -> None:
        self._last_line = line
        self._last_speech = self._clock()
        self._chat_orchestrator.speak_line(line)

    def _do_speak(self) -> None:
        line = self._line()
        if line:
            self._say(line)
        else:
            self._do_expression()

    def _walk(self) -> tuple[tuple[int, int], float]:
        low, high = ACTIVITY_PROFILES.get(self._profile(), ACTIVITY_PROFILES["lively"])[2:]
        distance = random.uniform(low, high)
        directions = _DIRECTIONS.copy()
        random.shuffle(directions)
        for direction in directions:
            dx, dy = direction
            length = math.hypot(dx, dy)
            if not length:
                continue
            if self._window is None:
                return direction, distance
            start = self._window.current_position()
            target = start + QtCore.QPoint(
                round(dx / length * distance), round(dy / length * distance)
            )
            actual = self._window.clamp_window_position(target) - start
            travel = math.hypot(actual.x(), actual.y())
            if travel >= min(24, distance / 2):
                return (actual.x(), actual.y()), travel
        return (0, 0), 0

    def _dispatch(self, action: Action) -> None:
        action.on_cancel = self._cancel_owned_walk
        self._owned_action = action
        self._action_dispatcher.dispatch(action)
        self._owned_movement = self._movement.active_movement

    def _cancel_owned_walk(self) -> None:
        if (
            self._owned_movement is not None
            and self._movement.active_movement is self._owned_movement
        ):
            self._movement.cancel_active_movement()

    def _do_walk_and_speak(self) -> None:
        self._start_walk(self._line())

    def _do_move(self) -> None:
        self._start_walk(None)

    def _start_walk(self, line: str | None) -> None:
        direction, distance = self._walk()
        if distance == 0:
            self._do_expression()
            return
        if self._action_dispatcher is not None and self._schedule is not None:
            self._dispatch(
                make_walk_and_speak_action(
                    self._movement,
                    self._schedule,
                    direction=direction,
                    distance=distance,
                    speak=(lambda: self._say(line)) if line else None,
                )
            )
        else:
            self._movement.apply_directional_walk(direction, distance)
            if line:
                self._say(line)

    def _do_expression(self) -> None:
        if self._effects():
            self._micro_effect(random.choice(["stretch", "wiggle"]))

    def _eligible_poses(self) -> list[str]:
        allowed = self._pose_keys()
        return [
            key
            for key in self._state_service.visible_state_keys()
            if key in allowed
            and not self._state_service.is_movement_only_state(key)
            and key != self._state_service.get_current_state_key()
        ]

    def _do_transition(self) -> None:
        keys = self._eligible_poses()
        if not keys or self._action_dispatcher is None or self._schedule is None:
            self._do_expression()
            return
        self._dispatch(
            Action(
                kind="companion_pose",
                phases=[
                    VisualPhase(
                        self._state_service,
                        random.choice(keys),
                        random.randint(1800, 3500),
                        self._schedule,
                    )
                ],
            )
        )
