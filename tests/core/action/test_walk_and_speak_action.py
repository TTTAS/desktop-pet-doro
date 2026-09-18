"""Tests for `make_walk_and_speak_action`.

The invariant that matters: the spoken line fires *after* the walk
completes, never before. The walk's trailing `WaitPhase` is what
enforces the ordering; the speech is one more `EffectPhase` behind it.
A walk that no-ops (already at the edge) still lets the line fire; a
walk that never completes (safety timeout) must not.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from doro_app.core.action import ActionDispatcher, make_walk_and_speak_action


class ManualScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, Callable[[], None]]] = []

    def __call__(self, ms: int, fn: Callable[[], None]) -> None:
        self.scheduled.append((int(ms), fn))

    def flush(self) -> None:
        while self.scheduled:
            _, fn = self.scheduled.pop(0)
            fn()

    def run_timeouts(self) -> None:
        """Fire only the non-zero (safety-timeout) callbacks."""
        pending = [(ms, fn) for ms, fn in self.scheduled if ms > 0]
        self.scheduled = [(ms, fn) for ms, fn in self.scheduled if ms == 0]
        for _, fn in pending:
            fn()


class FakeState:
    def __init__(self, key: str):
        self.key = key


class FakeStateService:
    def __init__(self, initial: str = "idle"):
        self.current = FakeState(initial)

    def get_current_state(self):
        return self.current

    def set_state(self, key: str, force: bool = False) -> bool:
        self.current = FakeState(key)
        return True


class FakeMovementAnimates:
    def __init__(self) -> None:
        self.has_active_movement = False
        self.listeners: list[Callable[[], None]] = []
        self.moved: list[tuple[int, int]] = []

    def apply_directional_walk(self, direction, distance=None):
        self.moved.append(direction)
        self.has_active_movement = True

    def add_completion_listener(self, cb):
        self.listeners.append(cb)

        def _unsub():
            if cb in self.listeners:
                self.listeners.remove(cb)

        return _unsub

    def finish(self):
        self.has_active_movement = False
        for cb in list(self.listeners):
            cb()


class FakeMovementNoOp:
    """Kick-off that never starts an animation (already at the edge)."""

    def __init__(self) -> None:
        self.has_active_movement = False
        self.moved: list[tuple[int, int]] = []

    def apply_directional_walk(self, direction, distance=None):
        self.moved.append(direction)
        # stays False → WaitPhase short-circuits to success

    def add_completion_listener(self, cb):  # pragma: no cover
        return lambda: None


@pytest.fixture
def scheduler():
    return ManualScheduler()


@pytest.fixture
def dispatcher(scheduler):
    return ActionDispatcher(state_service=FakeStateService(), schedule=scheduler)


def test_speaks_only_after_walk_completes(dispatcher, scheduler):
    movement = FakeMovementAnimates()
    spoken: list[str] = []
    dispatcher.dispatch(
        make_walk_and_speak_action(
            movement,
            scheduler,
            direction=(1, 0),
            speak=lambda: spoken.append("hi"),
        )
    )

    # Walked, but has NOT spoken yet — the WaitPhase is holding.
    assert movement.moved == [(1, 0)]
    assert spoken == []
    assert not dispatcher.is_idle

    movement.finish()
    assert spoken == ["hi"]
    assert dispatcher.is_idle


def test_silent_walk_has_no_speech_phase(dispatcher, scheduler):
    """speak=None builds a wander with no trailing speech — the walk still
    runs and completes, but nothing is ever spoken."""
    movement = FakeMovementAnimates()
    dispatcher.dispatch(
        make_walk_and_speak_action(
            movement,
            scheduler,
            direction=(1, 0),
            speak=None,
        )
    )
    assert movement.moved == [(1, 0)]
    movement.finish()
    assert dispatcher.is_idle  # walk drained cleanly, no extra phase hung


def test_no_op_walk_still_speaks(dispatcher, scheduler):
    movement = FakeMovementNoOp()
    spoken: list[str] = []
    dispatcher.dispatch(
        make_walk_and_speak_action(
            movement,
            scheduler,
            direction=(-1, 0),
            speak=lambda: spoken.append("hi"),
        )
    )
    scheduler.flush()

    assert movement.moved == [(-1, 0)]
    assert spoken == ["hi"]
    assert dispatcher.is_idle


def test_stuck_walk_never_speaks(dispatcher, scheduler):
    """If the walk never signals completion, the safety timeout fails the
    action and the line is not spoken from a walk that never arrived."""
    movement = FakeMovementAnimates()
    spoken: list[str] = []
    dispatcher.dispatch(
        make_walk_and_speak_action(
            movement,
            scheduler,
            direction=(0, 1),
            speak=lambda: spoken.append("hi"),
        )
    )
    # Never call movement.finish(); let the safety timeout win.
    scheduler.run_timeouts()

    assert spoken == []
    assert dispatcher.is_idle
