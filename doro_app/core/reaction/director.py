"""Run one timeline at a time. Preemption is priority-based."""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from .timeline import MoveStep, SpeakStep, StateStep, Step, Timeline, WaitStep


class StatePort(Protocol):
    def request_state(self, key: str, *, force: bool = False) -> bool: ...


class SpeakPort(Protocol):
    def __call__(self, text: str) -> None: ...


class SchedulePort(Protocol):
    def __call__(self, delay_ms: int, callback: Callable[[], None]) -> None: ...


class MovePort(Protocol):
    def __call__(self, direction: str, distance: float) -> None: ...


class ReactionDirector:
    """Plays a timeline through injected ports.

    ``schedule(delay_ms, callback)`` is how WaitStep yields. Production
    can pass ``QTimer.singleShot``; tests pass a manual queue.
    """

    def __init__(
        self,
        *,
        request_state: Callable[..., bool],
        speak: Callable[[str], None],
        schedule: SchedulePort,
        move: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._request_state = request_state
        self._speak = speak
        self._schedule = schedule
        self._move = move
        self._current: Optional[Timeline] = None
        self._index: int = 0
        self._generation: int = 0

    @property
    def is_playing(self) -> bool:
        return self._current is not None

    @property
    def current_name(self) -> Optional[str]:
        return None if self._current is None else self._current.name

    def play(self, timeline: Timeline) -> bool:
        """Start *timeline*.

        Returns False if a higher-priority timeline is already running.
        Equal or higher priority cancels the current one and starts.
        """
        if self._current is not None and timeline.priority < self._current.priority:
            return False
        self.cancel()
        self._current = timeline
        self._index = 0
        self._generation += 1
        self._run_next(self._generation)
        return True

    def cancel(self) -> None:
        """Drop the running timeline. In-flight wait callbacks become no-ops."""
        if self._current is None:
            return
        self._generation += 1
        self._current = None
        self._index = 0

    def _run_next(self, generation: int) -> None:
        if generation != self._generation or self._current is None:
            return
        if self._index >= len(self._current.steps):
            self._current = None
            self._index = 0
            return

        step = self._current.steps[self._index]
        self._index += 1
        self._execute(step, generation)

    def _execute(self, step: Step, generation: int) -> None:
        if isinstance(step, StateStep):
            self._request_state(step.key, force=step.force)
            self._run_next(generation)
            return
        if isinstance(step, SpeakStep):
            if step.text:
                self._speak(step.text)
            self._run_next(generation)
            return
        if isinstance(step, MoveStep):
            if self._move is not None:
                self._move(step.direction, step.distance)
            self._run_next(generation)
            return
        if isinstance(step, WaitStep):
            delay_ms = int(step.seconds * 1000)
            self._schedule(delay_ms, lambda: self._run_next(generation))
            return
        self._run_next(generation)
