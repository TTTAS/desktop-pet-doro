"""Tests for `make_click_action` — the dispatcher-side wrapper of
AutomationManager. Verifies the action surfaces preflight rejections as
failures and resolves on the manager's terminal outcome.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import pytest

from doro_app.core.action import (
    Action,
    ActionDispatcher,
    make_click_action,
)
from doro_app.core.automation.manager import ClickOutcome


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


class FakeAutomation:
    """Stand-in for AutomationManager exposing only what ClickAction touches."""

    def __init__(self, preflight: ClickOutcome = ClickOutcome.FIRED) -> None:
        self._preflight = preflight
        self._listeners: list[Callable[[ClickOutcome, str], None]] = []
        self.execute_calls = 0

    def execute_click(self) -> ClickOutcome:
        self.execute_calls += 1
        return self._preflight

    def add_outcome_listener(self, callback):
        self._listeners.append(callback)

        def unsub():
            if callback in self._listeners:
                self._listeners.remove(callback)
        return unsub

    def fire_outcome(self, outcome: ClickOutcome, detail: str = "") -> None:
        for cb in list(self._listeners):
            cb(outcome, detail)


class FakeState:
    def __init__(self, key: str):
        self.key = key


class FakeStateService:
    def __init__(self, initial: str = "idle"):
        self.current = FakeState(initial)
        self.calls: list[tuple] = []

    def get_current_state(self):
        return self.current

    def set_state(self, key: str, force: bool = False) -> bool:
        self.calls.append((key, bool(force)))
        self.current = FakeState(key)
        return True


@pytest.fixture
def scheduler():
    return ManualScheduler()


@pytest.fixture
def state_service():
    return FakeStateService()


@pytest.fixture
def dispatcher(state_service, scheduler):
    return ActionDispatcher(
        state_service=state_service,
        schedule=scheduler,
        failure_display_ms=500,
    )


class TestClickAction:
    def test_successful_click_routes_through_dispatcher(
        self, dispatcher, scheduler,
    ):
        automation = FakeAutomation()
        dispatcher.dispatch(make_click_action(automation, scheduler))

        # EffectPhase synchronously called execute_click; we're now in
        # the await-outcome phase (the 30s safety timer is queued).
        assert automation.execute_calls == 1
        assert not dispatcher.is_idle
        # Exactly one queued callback — the safety timeout. (The
        # dispatcher would only queue the failure-hold timer on failure.)
        assert len(scheduler.scheduled) == 1

        # Manager publishes a successful outcome — dispatcher unwinds.
        automation.fire_outcome(ClickOutcome.FIRED, "ok")
        assert dispatcher.is_idle

    def test_preflight_rejection_routes_to_failure(
        self, dispatcher, scheduler, state_service,
    ):
        automation = FakeAutomation(preflight=ClickOutcome.RATE_LIMITED)
        dispatcher.dispatch(make_click_action(automation, scheduler))

        # Preflight rejection raises in the EffectPhase → dispatcher
        # flips to click_failed and queues the failure-hold timer.
        # (No await-outcome timer was queued since we never made it
        # past the kick-off phase.)
        assert state_service.calls[0] == ("click_failed", True)
        scheduler.flush()  # drain the failure-hold (and any other) timers
        assert state_service.calls[-1] == ("idle", True)
        assert dispatcher.is_idle

    def test_non_fired_terminal_outcome_is_failure(
        self, dispatcher, scheduler, state_service,
    ):
        """Allowlist miss / esc abort / drag grace — none fired the click,
        all should surface as dispatcher-level failure (so the failure
        GIF wraps them)."""
        automation = FakeAutomation()
        dispatcher.dispatch(make_click_action(automation, scheduler))

        automation.fire_outcome(ClickOutcome.REJECTED_BY_ALLOWLIST, "no")
        # First call: click_failed shown by the failure path. The
        # 30s safety timer queued during the await phase is still in
        # the scheduler queue but its callback is already a no-op (the
        # await phase marked itself fired). Flushing drains both.
        assert state_service.calls[0] == ("click_failed", True)
        scheduler.flush()
        assert state_service.calls[-1] == ("idle", True)
        assert dispatcher.is_idle
