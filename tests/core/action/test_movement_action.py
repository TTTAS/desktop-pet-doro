"""Tests for `make_movement_action` and the `_MovementWaitPhase` short-circuit.

The key invariant covered here:

When `_kick_off` calls into the MovementManager but the manager
declines to start an animation (target already at the foot, parse
failure, etc.), the WaitPhase must not hang for `safety_timeout_ms`.
If it did, a click queued behind the movement would fire 30 s late —
which is exactly the 'click without walking' symptom this fix
addresses.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import pytest

from doro_app.core.action import ActionDispatcher, make_movement_action


class ManualScheduler:
    def __init__(self) -> None:
        self.scheduled: List[Tuple[int, Callable[[], None]]] = []

    def __call__(self, ms: int, fn: Callable[[], None]) -> None:
        self.scheduled.append((int(ms), fn))

    def run_next(self) -> None:
        _, fn = self.scheduled.pop(0)
        fn()

    def flush(self) -> None:
        while self.scheduled:
            _, fn = self.scheduled.pop(0)
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


class FakeMovementNoOp:
    """Movement manager whose handle_move_bracket runs but never starts
    an animation — mirrors the `_handle_target_move` early-return path
    when the target is essentially at the current foot."""

    def __init__(self) -> None:
        self.has_active_movement = False
        self.listeners: list[Callable[[], None]] = []
        self.kicked = False

    def handle_move_bracket(self, token: str, reports: list) -> bool:
        self.kicked = True
        # No-op: never sets has_active_movement, never fires listeners.
        return True

    def add_completion_listener(self, cb):  # pragma: no cover - shouldn't be hit
        self.listeners.append(cb)
        return lambda: self.listeners.remove(cb) if cb in self.listeners else None


class FakeMovementAnimates:
    """Movement manager that starts an animation on kick and surfaces a
    completion signal the WaitPhase can subscribe to."""

    def __init__(self) -> None:
        self.has_active_movement = False
        self.listeners: list[Callable[[], None]] = []

    def handle_move_bracket(self, token: str, reports: list) -> bool:
        self.has_active_movement = True
        return True

    def add_completion_listener(self, cb):
        self.listeners.append(cb)
        def _unsub():
            if cb in self.listeners:
                self.listeners.remove(cb)
        return _unsub

    def finish(self):
        """Test helper — simulate the movement reaching its target."""
        self.has_active_movement = False
        for cb in list(self.listeners):
            cb()


@pytest.fixture
def scheduler():
    return ManualScheduler()


@pytest.fixture
def dispatcher(scheduler):
    return ActionDispatcher(state_service=FakeStateService(), schedule=scheduler)


class TestMovementWaitPhaseShortCircuit:
    def test_no_op_movement_advances_via_schedule_0(self, dispatcher, scheduler):
        """When kick-off finishes without an active movement, the WaitPhase
        completes via `schedule(0, ...)` instead of waiting for the 30 s
        safety timeout. Otherwise the click queued behind would fire 30 s
        late at the unchanged position — visible to the user as 'Doro
        clicked without walking'."""
        movement = FakeMovementNoOp()
        action = make_movement_action(
            movement, scheduler, bracket_token="move:to;x=100;y=100",
        )
        dispatcher.dispatch(action)

        assert movement.kicked
        # The wait phase scheduled `schedule(0, on_done)`. No 30 s timeout
        # should be the only thing in the queue.
        zero_delays = [ms for ms, _ in scheduler.scheduled if ms == 0]
        assert zero_delays, "expected schedule(0, ...) short-circuit"

        scheduler.flush()
        # Action drained; dispatcher idle.
        assert dispatcher.is_idle

    def test_active_movement_waits_for_completion_signal(
        self, dispatcher, scheduler,
    ):
        """When kick-off DOES start a movement, the WaitPhase subscribes
        normally and only advances when `add_completion_listener` fires."""
        movement = FakeMovementAnimates()
        action = make_movement_action(
            movement, scheduler, bracket_token="move:to;x=400;y=300",
        )
        dispatcher.dispatch(action)

        # Subscribed, not advanced yet.
        assert len(movement.listeners) == 1
        assert not dispatcher.is_idle

        movement.finish()
        assert dispatcher.is_idle


class TestBracketReportForwarding:
    """`make_movement_action(bracket_token=...)` must surface validation
    reports via the `on_report` callback so the LLM sees its mistakes.
    The dispatcher path used to drop them into a throwaway list."""

    def test_reports_are_forwarded_to_on_report(self, dispatcher, scheduler):
        class FakeMovementWithReports:
            has_active_movement = False

            def __init__(self):
                self.listeners = []

            def handle_move_bracket(self, token, reports):
                reports.append("[移動錯誤] move:to 需要 x 與 y")
                return True

            def add_completion_listener(self, cb):  # pragma: no cover
                self.listeners.append(cb)
                return lambda: None

        movement = FakeMovementWithReports()
        captured: list[str] = []
        action = make_movement_action(
            movement,
            scheduler,
            bracket_token="move:to",
            on_report=captured.append,
        )
        dispatcher.dispatch(action)
        scheduler.flush()

        assert captured == ["[移動錯誤] move:to 需要 x 與 y"]

    def test_no_on_report_does_not_crash(self, dispatcher, scheduler):
        """Backwards-compat: callers that don't pass on_report still work."""
        movement = FakeMovementNoOp()
        action = make_movement_action(
            movement, scheduler, bracket_token="move:to;x=1;y=1"
        )
        dispatcher.dispatch(action)
        scheduler.flush()  # should not raise


class TestMovementThenClickOrdering:
    """End-to-end: movement that no-ops still releases a queued click
    promptly (the bug fix scenario)."""

    def test_queued_click_fires_after_no_op_movement(
        self, dispatcher, scheduler,
    ):
        from doro_app.core.action import (
            EffectPhase,
            Action,
        )

        movement = FakeMovementNoOp()
        click_fired: list[bool] = []
        click = Action(
            kind="click",
            phases=[EffectPhase(lambda: click_fired.append(True))],
        )

        dispatcher.dispatch(make_movement_action(
            movement, scheduler, bracket_token="move:to;x=100;y=100",
        ))
        dispatcher.dispatch(click)

        # Click should be waiting behind the movement action.
        assert click_fired == []

        scheduler.flush()
        # No-op movement drained → click ran.
        assert click_fired == [True]
        assert dispatcher.is_idle
