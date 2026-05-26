"""Tests for AutomationManager — the wind-up + allowlist + kill-switch flow.

These tests use:
  - FakeInputBackend to record clicks / drive Esc and mouse-button state
  - FakeAutomationWindow to simulate Doro's foot position
  - ManualScheduler so the wind-up timer expires synchronously
  - ClockStub for rate-limit assertions

No Qt event loop is started.
"""

from __future__ import annotations

import pytest

from doro_app.core.automation.manager import AutomationManager, ClickOutcome


# ────────────────────────────────────────────────────────────────────────
# Happy path / opt-in
# ────────────────────────────────────────────────────────────────────────


class TestEnabledGate:
    def test_disabled_short_circuits_before_wind_up(self, config_stub, fake_window, fake_backend, scheduler, clock, coord_stub):
        config_stub.update_automation(mouse_enabled=False)
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )

        outcome = manager.execute_click()

        assert outcome == ClickOutcome.DISABLED
        # No wind-up was scheduled, no GIF lock was taken.
        assert scheduler.scheduled == []
        coord_stub.begin.assert_not_called()
        assert fake_backend.click_calls == []


class TestAllowlistHit:
    def test_click_fires_at_doro_foot_when_class_allowed(
        self, manager, fake_backend, fake_window, scheduler, coord_stub
    ):
        fake_backend.set_window_class("Firefox")
        fake_window.move_foot_to((700, 800), physical=(700, 800))

        # Trigger execute_click — this schedules the wind-up.
        assert manager.execute_click() == ClickOutcome.FIRED  # provisional
        coord_stub.begin.assert_called_once()
        assert manager.is_busy is True

        # Re-aim Doro mid-wind-up — final click should sample CURRENT pos.
        fake_window.move_foot_to((900, 1000), physical=(900, 1000))

        # Fire the wind-up timer.
        scheduler.flush()

        assert fake_backend.click_calls == [(900, 1000)]
        assert manager.outcomes[-1] == ClickOutcome.FIRED
        coord_stub.end.assert_called_once()
        assert manager.is_busy is False

    def test_transparent_toggle_brackets_the_click(self, manager, fake_backend, fake_window, scheduler):
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        # Self-clicking trap defense: WA_TransparentForMouseEvents must be
        # toggled True before the click and back to False after.
        assert fake_window.transparent_toggles == [True, False]


class TestAllowlistMiss:
    @pytest.mark.parametrize("bad_class", ["KeePassXC", "Bitwarden", None, "", "Gedit"])
    def test_miss_aborts_without_click(self, manager, fake_backend, scheduler, coord_stub, bad_class):
        fake_backend.set_window_class(bad_class)
        manager.execute_click()
        scheduler.flush()

        assert fake_backend.click_calls == []
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST
        # The transition lock MUST still be released on this exit path.
        coord_stub.end.assert_called_once()
        assert manager.is_busy is False

    def test_redirect_after_drag_to_non_allowlisted_app(
        self, manager, fake_backend, fake_window, scheduler
    ):
        # Doro starts on Firefox but is dragged to KeePassXC during wind-up.
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        # Simulate the drag: foot moves AND window-class changes.
        fake_window.move_foot_to((1200, 60), physical=(1200, 60))
        fake_backend.set_window_class("KeePassXC")

        scheduler.flush()

        assert fake_backend.click_calls == []
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST


# ────────────────────────────────────────────────────────────────────────
# Rate limiting + busy
# ────────────────────────────────────────────────────────────────────────


class TestRateLimit:
    def test_busy_during_wind_up(self, manager, fake_backend, scheduler):
        fake_backend.set_window_class("Firefox")
        assert manager.execute_click() == ClickOutcome.FIRED  # provisional
        # Second call mid-wind-up is BUSY, not RATE_LIMITED.
        assert manager.execute_click() == ClickOutcome.BUSY
        # Only one wind-up was scheduled.
        assert len(scheduler.scheduled) == 1
        scheduler.flush()

    def test_rate_limited_after_recent_click(
        self, manager, fake_backend, scheduler, clock
    ):
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()  # first click fires
        assert manager.outcomes[-1] == ClickOutcome.FIRED

        # Immediately try again — should be rate-limited.
        outcome = manager.execute_click()
        assert outcome == ClickOutcome.RATE_LIMITED
        assert scheduler.scheduled == []

        # Advance past the rate limit and it works again.
        clock.advance(3.0)
        outcome2 = manager.execute_click()
        assert outcome2 == ClickOutcome.FIRED  # provisional


# ────────────────────────────────────────────────────────────────────────
# Drag grace
# ────────────────────────────────────────────────────────────────────────


class TestDragGrace:
    def test_grace_waits_for_release_then_fires(
        self, manager, fake_backend, scheduler, clock
    ):
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True

        manager.execute_click()
        # First scheduled callback is the wind-up expiry.
        scheduler.run_next()
        # User is still holding → manager scheduled a grace check, no click yet.
        assert fake_backend.click_calls == []
        assert manager.is_busy is True
        assert len(scheduler.scheduled) == 1  # the 50ms grace check

        # Release the button before grace deadline.
        fake_backend.left_button_pressed = False
        scheduler.run_next()  # grace check sees released → fires

        assert fake_backend.click_calls != []
        assert manager.outcomes[-1] == ClickOutcome.FIRED

    def test_grace_exceeded_means_no_click(
        self, manager, fake_backend, scheduler, clock, coord_stub
    ):
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True

        manager.execute_click()
        scheduler.run_next()  # wind-up expiry → enters grace
        # User holds past the 1s grace window.
        clock.advance(2.0)
        scheduler.run_next()  # grace check times out

        assert fake_backend.click_calls == []
        assert manager.outcomes[-1] == ClickOutcome.DRAG_GRACE_EXCEEDED
        # Lock STILL released — the bug from the plan that we must avoid.
        coord_stub.end.assert_called_once()
        assert manager.is_busy is False


# ────────────────────────────────────────────────────────────────────────
# Esc abort + kill-switch
# ────────────────────────────────────────────────────────────────────────


class TestEscAbort:
    def test_esc_during_wind_up_cancels_click(
        self, manager, fake_backend, scheduler, coord_stub
    ):
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        # Esc arrives before wind-up timer expires.
        fake_backend.press_esc()
        scheduler.flush()

        assert fake_backend.click_calls == []
        assert manager.outcomes[-1] == ClickOutcome.ABORTED_BY_ESC
        coord_stub.end.assert_called_once()


class TestKillSwitch:
    def test_three_esc_in_window_engages_kill_switch(
        self, manager, fake_backend, config_stub, clock
    ):
        # Three Esc presses close together.
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()

        assert manager.is_kill_switch_engaged is True
        # Config was rewritten to disable automation.
        assert config_stub.automation.mouse_enabled is False
        assert config_stub.save_called >= 1

    def test_kill_switch_blocks_subsequent_clicks(
        self, manager, fake_backend, config_stub, clock
    ):
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()

        outcome = manager.execute_click()
        assert outcome == ClickOutcome.KILL_SWITCH

    def test_esc_outside_window_does_not_engage(
        self, manager, fake_backend, config_stub, clock
    ):
        # Three presses, but one is too far from the others.
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()
        clock.advance(5.0)  # well beyond the rolling window
        fake_backend.press_esc()

        assert manager.is_kill_switch_engaged is False


# ────────────────────────────────────────────────────────────────────────
# Cross-cutting invariants
# ────────────────────────────────────────────────────────────────────────


class TestTransitionLockRelease:
    """Every exit path must call transition_coordinator.end() exactly once
    per execute_click invocation. Forgetting this leaks the lock and
    causes idle GIF rotation to stop forever — the loudest bug from the plan.
    """

    def _arm_and_flush(self, manager, fake_backend, scheduler, *, klass="Firefox"):
        fake_backend.set_window_class(klass)
        manager.execute_click()
        scheduler.flush()

    def test_fired_path_releases(self, manager, fake_backend, scheduler, coord_stub):
        self._arm_and_flush(manager, fake_backend, scheduler, klass="Firefox")
        coord_stub.end.assert_called_once()

    def test_allowlist_miss_releases(self, manager, fake_backend, scheduler, coord_stub):
        self._arm_and_flush(manager, fake_backend, scheduler, klass="KeePassXC")
        coord_stub.end.assert_called_once()

    def test_esc_abort_releases(self, manager, fake_backend, scheduler, coord_stub):
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        fake_backend.press_esc()
        scheduler.flush()
        coord_stub.end.assert_called_once()

    def test_grace_exceeded_releases(self, manager, fake_backend, scheduler, clock, coord_stub):
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True
        manager.execute_click()
        scheduler.run_next()  # wind-up → enters grace
        clock.advance(2.0)
        scheduler.run_next()  # grace times out
        coord_stub.end.assert_called_once()
