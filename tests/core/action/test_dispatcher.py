"""Tests for the ActionDispatcher + Phase abstractions.

These cover the serialization guarantee that replaced the
defer/polling loop inside AutomationManager: when a MovementAction is
in flight, a ClickAction dispatched after it must not start until the
movement listener fires. The test doubles below stand in for the real
StateService / MovementManager so the dispatcher can be exercised
purely synchronously through a manual scheduler.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import pytest

from doro_app.core.action import (
    Action,
    ActionDispatcher,
    EffectPhase,
    VisualPhase,
    WaitPhase,
)


class ManualScheduler:
    """Same shape as the automation tests' ManualScheduler: records
    (ms, callback) and runs them on demand. Keeps tests deterministic
    without spinning a Qt event loop."""

    def __init__(self) -> None:
        self.scheduled: List[Tuple[int, Callable[[], None]]] = []

    def __call__(self, ms: int, fn: Callable[[], None]) -> None:
        self.scheduled.append((int(ms), fn))

    def run_next(self) -> None:
        assert self.scheduled, "no callback scheduled"
        _, fn = self.scheduled.pop(0)
        fn()

    def flush(self) -> None:
        while self.scheduled:
            _, fn = self.scheduled.pop(0)
            fn()


class FakeState:
    """Minimal duck-type for what dispatcher calls on `state_service`."""

    def __init__(self, key: str):
        self.key = key


class FakeStateService:
    """Records every set_state for assertions; refuses changes if
    `refuse_keys` contains the target — used to test the dispatcher's
    fail-safe path that nullifies pre_action_state on a refused set."""

    def __init__(self, initial: str = "idle"):
        self.current = FakeState(initial)
        self.calls: list[Tuple[str, bool]] = []
        self.refuse_keys: set[str] = set()

    def get_current_state(self):
        return self.current

    def set_state(self, key: str, force: bool = False) -> bool:
        self.calls.append((key, bool(force)))
        if key in self.refuse_keys:
            return False
        self.current = FakeState(key)
        return True


@pytest.fixture
def scheduler():
    return ManualScheduler()


@pytest.fixture
def state_service():
    return FakeStateService(initial="idle")


@pytest.fixture
def dispatcher(state_service, scheduler):
    return ActionDispatcher(
        state_service=state_service,
        schedule=scheduler,
        failure_display_ms=500,
    )


# ─────────────────────────────────────────────────────────────────────
# Basic lifecycle
# ─────────────────────────────────────────────────────────────────────


class TestBasicLifecycle:
    def test_idle_dispatcher_has_no_current(self, dispatcher):
        assert dispatcher.is_idle
        assert dispatcher.current is None

    def test_single_effect_action_runs_and_restores(self, dispatcher, state_service):
        marker: list[str] = []
        action = Action(
            kind="test",
            phases=[EffectPhase(lambda: marker.append("ran"))],
        )
        dispatcher.dispatch(action)
        assert marker == ["ran"]
        # EffectPhase doesn't change state, so the dispatcher's final
        # set_state(pre_state) is skipped (current == pre).
        assert state_service.calls == []
        assert dispatcher.is_idle

    def test_visual_phase_sets_then_restores(self, dispatcher, state_service, scheduler):
        action = Action(
            kind="test",
            phases=[VisualPhase(state_service, "click_action", 1500, scheduler)],
        )
        dispatcher.dispatch(action)
        # Phase started: state flipped to click_action.
        assert state_service.calls == [("click_action", True)]
        assert not dispatcher.is_idle

        scheduler.run_next()  # VisualPhase timer fires
        # Dispatcher restores to "idle" (the captured pre_action_state).
        assert state_service.calls == [("click_action", True), ("idle", True)]
        assert dispatcher.is_idle


# ─────────────────────────────────────────────────────────────────────
# Serialization: movement → click ordering
# ─────────────────────────────────────────────────────────────────────


class TestSerialization:
    """The core guarantee — replaces the old defer/polling path."""

    def test_second_action_waits_for_first(self, dispatcher, state_service):
        markers: list[str] = []

        # A blocking phase that only completes when we tell it to.
        class _Latch:
            def __init__(self):
                self._on_done = None
                self._fired = False

            def start(self, on_done, on_fail):
                self._on_done = on_done

            def cancel(self):
                pass

            def release(self):
                if not self._fired and self._on_done:
                    self._fired = True
                    self._on_done()

        latch = _Latch()
        first = Action(
            kind="first",
            phases=[latch, EffectPhase(lambda: markers.append("first-end"))],
        )
        second = Action(
            kind="second",
            phases=[EffectPhase(lambda: markers.append("second"))],
        )

        dispatcher.dispatch(first)
        dispatcher.dispatch(second)

        # Latch is open — first is mid-phase, second hasn't started.
        assert markers == []
        assert dispatcher.current is first
        assert dispatcher.queue_depth == 1

        latch.release()
        # First drains, then second runs in the same tick.
        assert markers == ["first-end", "second"]
        assert dispatcher.is_idle

    def test_movement_then_click_pattern(self, dispatcher, state_service, scheduler):
        """The headline scenario: dispatch movement, then click; click must
        not run until movement's completion listener fires.
        """
        movement_listeners: list[Callable[[], None]] = []

        def subscribe(cb):
            movement_listeners.append(cb)

            def unsub():
                if cb in movement_listeners:
                    movement_listeners.remove(cb)

            return unsub

        click_fired = {"v": False}

        movement = Action(
            kind="movement",
            phases=[
                EffectPhase(lambda: None),  # "kick off"
                WaitPhase(subscribe=subscribe, schedule=scheduler, safety_timeout_ms=30_000),
            ],
        )
        click = Action(
            kind="click",
            phases=[EffectPhase(lambda: click_fired.__setitem__("v", True))],
        )

        dispatcher.dispatch(movement)
        dispatcher.dispatch(click)

        # Movement is waiting on the listener; click has not run.
        assert click_fired["v"] is False
        assert dispatcher.current is movement

        # Movement completes — listener fires, dispatcher pumps to click.
        for listener in list(movement_listeners):
            listener()
        assert click_fired["v"] is True
        assert dispatcher.is_idle


# ─────────────────────────────────────────────────────────────────────
# Failure handling
# ─────────────────────────────────────────────────────────────────────


class TestFailurePath:
    def test_failed_phase_shows_failure_state_then_restores(
        self,
        dispatcher,
        state_service,
        scheduler,
    ):
        def boom():
            raise RuntimeError("nope")

        action = Action(
            kind="click",
            phases=[EffectPhase(boom)],
            failure_state_key="click_failed",
        )
        dispatcher.dispatch(action)
        # Failure path: dispatcher set state to click_failed immediately.
        assert state_service.calls == [("click_failed", True)]
        # Dispatcher scheduled the failure-display delay; not idle yet.
        assert not dispatcher.is_idle

        scheduler.run_next()  # failure hold expires
        # Then restore to idle (pre_action_state).
        assert state_service.calls == [
            ("click_failed", True),
            ("idle", True),
        ]
        assert dispatcher.is_idle

    def test_failed_with_no_failure_key_just_restores(
        self,
        dispatcher,
        state_service,
    ):
        def boom():
            raise RuntimeError("nope")

        action = Action(
            kind="movement",
            phases=[EffectPhase(boom)],
            failure_state_key=None,
        )
        dispatcher.dispatch(action)
        # No failure state means dispatcher goes straight to restore.
        # We started at idle and never set anything, so the restore is a no-op.
        assert state_service.calls == []
        assert dispatcher.is_idle


# ─────────────────────────────────────────────────────────────────────
# Cancellation
# ─────────────────────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_during_visual_phase_restores_without_failure(
        self,
        dispatcher,
        state_service,
        scheduler,
    ):
        action = Action(
            kind="click",
            phases=[VisualPhase(state_service, "click_action", 1500, scheduler)],
            failure_state_key="click_failed",
        )
        dispatcher.dispatch(action)
        assert state_service.calls == [("click_action", True)]

        dispatcher.cancel_current("esc")
        # Restored to idle directly — no failure GIF.
        assert state_service.calls == [
            ("click_action", True),
            ("idle", True),
        ]
        assert dispatcher.is_idle

    def test_cancel_clears_pending_queue(self, dispatcher, state_service, scheduler):
        # Movement is "in flight" via a never-firing latch; click is queued.
        class _Latch:
            def start(self, on_done, on_fail):
                pass

            def cancel(self):
                pass

        first = Action(kind="movement", phases=[_Latch()])
        click_fired = {"v": False}
        second = Action(
            kind="click",
            phases=[EffectPhase(lambda: click_fired.__setitem__("v", True))],
        )

        dispatcher.dispatch(first)
        dispatcher.dispatch(second)

        dispatcher.cancel_current("esc")
        assert click_fired["v"] is False  # queued click never runs
        assert dispatcher.is_idle

    def test_stale_failure_hold_does_not_finish_next_action(
        self,
        dispatcher,
        state_service,
        scheduler,
    ):
        """Generation token guard.

        Action A enters its failure-GIF hold (1.5s timer scheduled). Esc
        cancels A; the user immediately dispatches action B. When A's
        stale failure-hold timer eventually fires, it must recognise
        that the dispatcher has moved on and refuse to finish B's phase.
        Without the generation check, the stale callback would call
        `_restore_and_finish`, killing B mid-flight.
        """

        def boom():
            raise RuntimeError("nope")

        action_a = Action(
            kind="click",
            phases=[EffectPhase(boom)],
            failure_state_key="click_failed",
        )
        dispatcher.dispatch(action_a)
        # A's failure GIF is up; the hold timer is queued but not yet run.
        assert state_service.calls == [("click_failed", True)]
        assert not dispatcher.is_idle

        # Esc during the hold window — A unwinds, queue clears.
        dispatcher.cancel_current("esc")
        assert dispatcher.is_idle
        # idle restore happened
        assert state_service.calls[-1] == ("idle", True)

        # New action B uses a never-firing latch so we can observe it
        # staying current after the stale timer fires.
        class _Latch:
            def __init__(self):
                self.cancelled = False
                self.done_cb = None

            def start(self, on_done, on_fail):
                self.done_cb = on_done

            def cancel(self):
                self.cancelled = True

        latch = _Latch()
        action_b = Action(kind="movement", phases=[latch])
        dispatcher.dispatch(action_b)
        assert dispatcher.current is action_b
        calls_before = list(state_service.calls)

        # A's stale failure-hold timer finally fires.
        scheduler.run_next()

        # B is untouched: still current, latch not cancelled, no state churn.
        assert dispatcher.current is action_b
        assert latch.cancelled is False
        assert state_service.calls == calls_before


# ─────────────────────────────────────────────────────────────────────
# WaitPhase safety timeout
# ─────────────────────────────────────────────────────────────────────


class TestWaitPhaseTimeout:
    def test_safety_timeout_surfaces_as_failure(
        self,
        dispatcher,
        state_service,
        scheduler,
    ):
        def subscribe(cb):
            # Never fires the listener — simulates stuck movement.
            return lambda: None

        action = Action(
            kind="movement",
            phases=[
                WaitPhase(
                    subscribe=subscribe,
                    schedule=scheduler,
                    safety_timeout_ms=30_000,
                ),
            ],
            failure_state_key=None,  # movement has no failure GIF
        )
        dispatcher.dispatch(action)

        # The scheduler should have one pending callback — the 30s timeout.
        assert len(scheduler.scheduled) == 1
        assert scheduler.scheduled[0][0] == 30_000

        scheduler.run_next()  # timeout fires
        # No failure key — dispatcher just restored.
        assert dispatcher.is_idle
