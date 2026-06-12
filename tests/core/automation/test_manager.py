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

from .conftest import ConfigManagerStub


# ────────────────────────────────────────────────────────────────────────
# Happy path / opt-in
# ────────────────────────────────────────────────────────────────────────


class TestEnabledGate:
    def test_disabled_short_circuits_before_wind_up(self, fake_clicker, config_stub, fake_window, fake_backend, scheduler, clock, coord_stub):
        config_stub.update_automation(mouse_enabled=False)
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )

        outcome = manager.execute_click()

        assert outcome == ClickOutcome.DISABLED
        # No wind-up was scheduled, no GIF lock was taken.
        assert scheduler.scheduled == []
        coord_stub.begin.assert_not_called()
        assert fake_clicker.invoke_calls == []


class TestAllowlistHit:
    def test_click_fires_at_doro_foot_when_class_allowed(
        self, fake_clicker, manager, fake_backend, fake_window, scheduler, coord_stub
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

        assert fake_clicker.invoke_calls == [(900, 1000)]
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
    def test_miss_aborts_without_click(self, fake_clicker, manager, fake_backend, scheduler, coord_stub, bad_class):
        fake_backend.set_window_class(bad_class)
        manager.execute_click()
        scheduler.flush()

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST
        # The transition lock MUST still be released on this exit path.
        coord_stub.end.assert_called_once()
        assert manager.is_busy is False

    def test_redirect_after_drag_to_non_allowlisted_app(
        self, fake_clicker, manager, fake_backend, fake_window, scheduler
    ):
        # Doro starts on Firefox but is dragged to KeePassXC during wind-up.
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        # Simulate the drag: foot moves AND window-class changes.
        fake_window.move_foot_to((1200, 60), physical=(1200, 60))
        fake_backend.set_window_class("KeePassXC")

        scheduler.flush()

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST

    @pytest.mark.parametrize(
        "win_class",
        [
            "Chrome_WidgetWin_1",          # Windows Chrome main hwnd
            "Chrome_WidgetWin_0",
            "Chrome_RenderWidgetHostHWND",  # Chrome subwindow
            "CHROME_WIDGETWIN_1",          # case-insensitive
        ],
    )
    def test_prefix_match_lets_chrome_family_through(
        self, fake_clicker, fake_window, fake_backend, coord_stub, scheduler, clock, win_class
    ):
        """Allowlist entries are prefixes, so a single `Chrome` entry covers
        all the Windows-side Chrome_* widget classes Chrome / Edge / Brave
        actually report at the foreground."""
        from doro_app.core.automation.manager import AutomationManager

        config = ConfigManagerStub(mouse_enabled=True, allowlist=("Chrome",))
        manager = AutomationManager(
            config_manager=config,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class(win_class)
        manager.execute_click()
        scheduler.flush()

        assert manager.outcomes[-1] == ClickOutcome.FIRED, (
            f"{win_class!r} should match the `Chrome` prefix"
        )

    def test_prefix_match_does_not_match_unrelated_class(
        self, fake_clicker, fake_window, fake_backend, coord_stub, scheduler, clock
    ):
        """Prefix match is anchored, so `Firefox` doesn't accidentally allow
        e.g. `Foo_Firefox_Bar` mid-string."""
        from doro_app.core.automation.manager import AutomationManager

        config = ConfigManagerStub(mouse_enabled=True, allowlist=("Firefox",))
        manager = AutomationManager(
            config_manager=config,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("NotFirefoxAtAll")
        manager.execute_click()
        scheduler.flush()
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST


class TestForegroundVerification:
    """The allowlist guards which class can be invoked, but the same
    class can sit under the cursor on a background window. The
    foreground-handle check refuses those — the user almost certainly
    didn't intend Doro to act on a window they aren't focused on."""

    def test_background_allowlisted_window_is_rejected(
        self, fake_clicker, manager, fake_backend, scheduler, coord_stub,
    ):
        fake_backend.set_window_class("Firefox")
        # Same class lives under the click point AND in foreground, but
        # they are different windows (e.g. a background Firefox).
        fake_backend.handle_at_default = 100
        fake_backend.foreground_handle = 200

        manager.execute_click()
        scheduler.flush()

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.REJECTED_BY_ALLOWLIST
        coord_stub.end.assert_called_once()

    def test_matching_foreground_is_accepted(
        self, fake_clicker, manager, fake_backend, scheduler,
    ):
        fake_backend.set_window_class("Firefox")
        fake_backend.handle_at_default = 100
        fake_backend.foreground_handle = 100

        manager.execute_click()
        scheduler.flush()

        assert fake_clicker.invoke_calls != []
        assert manager.outcomes[-1] == ClickOutcome.FIRED

    def test_missing_handle_skips_check(
        self, fake_clicker, manager, fake_backend, scheduler,
    ):
        """When the backend can't supply hwnds (X11/macOS), fall back to
        the class-only gate — same as before this fix."""
        fake_backend.set_window_class("Firefox")
        fake_backend.handle_at_default = None
        fake_backend.foreground_handle = None

        manager.execute_click()
        scheduler.flush()

        assert manager.outcomes[-1] == ClickOutcome.FIRED


class TestMultiMonitorClamp:
    """`screen_geometry_physical` carries an origin; secondary monitors
    with non-zero origin shouldn't have legitimate coords clamped into
    the primary monitor."""

    def test_target_inside_secondary_monitor_passes_through(
        self, fake_clicker, fake_backend, coord_stub, config_stub, scheduler, clock,
    ):
        # Secondary monitor at x=1920..3839.
        from doro_app.core.automation.fakes import FakeAutomationWindow

        window = FakeAutomationWindow(
            foot_logical=(2500, 500),
            foot_physical=(2500, 500),
            screen_size=(1920, 1080),
            screen_origin=(1920, 0),
        )
        config = ConfigManagerStub(mouse_enabled=True, allowlist=("Firefox",))
        manager = AutomationManager(
            config_manager=config,
            window=window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()

        # Coord must NOT have been clamped to 0..1919.
        assert fake_clicker.invoke_calls == [(2500, 500)]


class TestNotInvocable:
    """The cursor-free click path falls back to NOT_INVOCABLE (no
    synthetic mouse event) when the UIA InvokePattern is unavailable —
    either the clicker port is absent or the element under (x, y)
    doesn't expose Invoke (canvas, custom widgets). No cursor movement
    in any case, so the LLM can retry without disrupting the user."""

    def test_no_clicker_wired_records_not_invocable(
        self, config_stub, fake_window, fake_backend, coord_stub, scheduler, clock,
    ):
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            transition_coordinator=coord_stub,
            # a11y_clicker intentionally omitted — production wiring on
            # platforms without a UIA backend should still terminate cleanly.
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()

        assert manager.outcomes[-1] == ClickOutcome.NOT_INVOCABLE
        # Allowlist + transition lock both still ran their exit path.
        coord_stub.end.assert_called_once()

    def test_clicker_returns_false_records_not_invocable(
        self, config_stub, fake_window, fake_backend, coord_stub, scheduler, clock,
    ):
        from doro_app.core.automation.fakes import FakeA11yClicker
        clicker = FakeA11yClicker(should_succeed=False)
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            transition_coordinator=coord_stub,
            a11y_clicker=clicker,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()

        # The clicker WAS asked — recording the failure path went through
        # the invoke call.
        assert clicker.invoke_calls == [(500, 500)]
        assert manager.outcomes[-1] == ClickOutcome.NOT_INVOCABLE

    def test_allowlist_miss_short_circuits_before_invoke(
        self, config_stub, fake_window, fake_backend, coord_stub, scheduler, clock,
    ):
        """Allowlist is the first defence — if the target class isn't
        allowed we never even ask the clicker."""
        from doro_app.core.automation.fakes import FakeA11yClicker
        clicker = FakeA11yClicker(should_succeed=True)
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            transition_coordinator=coord_stub,
            a11y_clicker=clicker,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("KeePassXC")
        manager.execute_click()
        scheduler.flush()

        assert clicker.invoke_calls == []  # never reached
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
        self, fake_clicker, manager, fake_backend, scheduler, clock
    ):
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True

        manager.execute_click()
        # First scheduled callback is the wind-up expiry.
        scheduler.run_next()
        # User is still holding → manager scheduled a grace check, no click yet.
        assert fake_clicker.invoke_calls == []
        assert manager.is_busy is True
        assert len(scheduler.scheduled) == 1  # the 50ms grace check

        # Release the button before grace deadline.
        fake_backend.left_button_pressed = False
        scheduler.run_next()  # grace check sees released → fires

        assert fake_clicker.invoke_calls != []
        assert manager.outcomes[-1] == ClickOutcome.FIRED

    def test_grace_exceeded_means_no_click(
        self, fake_clicker, manager, fake_backend, scheduler, clock, coord_stub
    ):
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True

        manager.execute_click()
        scheduler.run_next()  # wind-up expiry → enters grace
        # User holds past the 1s grace window.
        clock.advance(2.0)
        scheduler.run_next()  # grace check times out

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.DRAG_GRACE_EXCEEDED
        # Lock STILL released — the bug from the plan that we must avoid.
        coord_stub.end.assert_called_once()
        assert manager.is_busy is False


# ────────────────────────────────────────────────────────────────────────
# Esc abort + kill-switch
# ────────────────────────────────────────────────────────────────────────


class TestEscAbort:
    def test_esc_during_wind_up_cancels_click(
        self, fake_clicker, manager, fake_backend, scheduler, coord_stub
    ):
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        # Esc arrives before wind-up timer expires.
        fake_backend.press_esc()
        scheduler.flush()

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.ABORTED_BY_ESC
        coord_stub.end.assert_called_once()

    def test_drag_cancels_in_flight_click(
        self, fake_clicker, manager, fake_backend, scheduler, coord_stub
    ):
        """User drags Doro while a click is in wind-up.

        Without `cancel_pending_click`, the wind-up timer continues, the
        manager falls back to the post-drag foot position, and the
        click fires somewhere the user didn't intend. With it, the
        in-flight click aborts the same way Esc would (just without
        bumping the kill-switch press count).
        """
        fake_backend.set_window_class("Firefox")
        manager.execute_click()

        # Drag interrupts mid-wind-up.
        cancelled = manager.cancel_pending_click("drag")
        scheduler.flush()

        assert cancelled is True
        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.ABORTED_BY_ESC
        # Drag must NOT have bumped the Esc-counter towards kill-switch.
        assert manager._esc_press_times == []

    def test_cancel_pending_click_returns_false_when_idle(self, manager):
        assert manager.cancel_pending_click("drag") is False

    def test_esc_set_just_before_fire_aborts(
        self, fake_clicker, manager, fake_backend, scheduler, coord_stub
    ):
        """M3: an Esc whose flag is observed at `_fire_now` entry must
        abort even if the wind-up timer already left its own entry check.
        """
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        # Wind-up timer expires; the bare wind-up path used to be the
        # only Esc check. Simulate Esc that arrives between the timer
        # firing and _fire_now reading the flag.
        manager._abort_pending = True
        manager._complete_wind_up_for_test()

        assert fake_clicker.invoke_calls == []
        assert manager.outcomes[-1] == ClickOutcome.ABORTED_BY_ESC


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

    def test_reset_kill_switch_re_arms_manager(
        self, manager, fake_backend, config_stub, clock
    ):
        """The settings dialog can re-arm clicking without an app restart."""
        # Engage by triple-Esc.
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()
        clock.advance(0.1)
        fake_backend.press_esc()
        assert manager.is_kill_switch_engaged is True

        # Simulate the user re-ticking mouse_enabled in the settings dialog.
        config_stub.update_automation(mouse_enabled=True)
        manager.reset_kill_switch()

        assert manager.is_kill_switch_engaged is False
        # Next click goes through (provisionally accepted as FIRED).
        assert manager.execute_click() == ClickOutcome.FIRED

    def test_execute_click_self_heals_kill_switch_when_config_says_enabled(
        self, manager, config_stub, clock
    ):
        """Race-protection self-heal.

        If config got persisted as mouse_enabled=True (settings dialog
        wrote it) but the manager's kill-switch flag was never cleared
        (e.g. dialog couldn't reach the manager), the next click
        observation should clear the flag instead of dropping silently.
        """
        # Engage kill-switch directly.
        manager._kill_switch_engaged = True
        # Make sure config says enabled (the dialog already persisted it).
        config_stub.update_automation(mouse_enabled=True)

        outcome = manager.execute_click()

        assert outcome == ClickOutcome.FIRED
        assert manager.is_kill_switch_engaged is False

    def test_esc_marshal_runs_callback_on_marshalled_thread(
        self,
        config_stub,
        fake_window,
        fake_backend,
        fake_clicker,
        coord_stub,
        scheduler,
        clock,
    ):
        """Esc from the backend (off-thread in production) must NOT touch
        manager state synchronously — it must be queued through `marshal`.

        Without the trampoline, `_on_esc_pressed` would mutate state on
        the pynput listener thread and step on Qt-bound work running on
        the main thread.
        """
        deferred: list = []
        mgr = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            transition_coordinator=coord_stub,
            a11y_clicker=fake_clicker,
            schedule=scheduler,
            clock=clock,
            marshal=deferred.append,
        )

        # Wind a click up so the backend Esc has something to abort.
        assert mgr.execute_click() == ClickOutcome.FIRED  # provisional
        assert mgr._abort_pending is False

        fake_backend.press_esc()
        # Marshal received the callback but hasn't run it yet — state
        # MUST still be untouched.
        assert len(deferred) == 1
        assert mgr._abort_pending is False
        assert mgr._esc_press_times == []

        # Running it on the (simulated) main thread is what actually
        # applies the Esc.
        deferred[0]()
        assert mgr._abort_pending is True
        assert len(mgr._esc_press_times) == 1


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


class TestWindUpAnimator:
    """The wind_up_animator port plays the click GIF during wind-up.

    Like transition_coordinator, every exit path MUST call ``end()``
    exactly once — otherwise the click_action display state stays stuck
    and Doro looks frozen.
    """

    def _build_manager(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        from doro_app.core.automation.manager import AutomationManager
        return AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            wind_up_animator=wind_up_animator,
            schedule=scheduler,
            clock=clock,
        )

    def test_begin_fires_when_wind_up_starts(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()

        # begin() must run before the wind-up timer expires so the click
        # GIF is on screen for the full ~1.5s, not just at fire time.
        assert wind_up_animator.begin_calls == 1
        assert wind_up_animator.end_calls == 0

    def test_fired_path_calls_end_exactly_once(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert wind_up_animator.end_calls == 1

    def test_allowlist_miss_still_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        fake_backend.set_window_class("KeePassXC")
        manager.execute_click()
        scheduler.flush()
        assert wind_up_animator.end_calls == 1

    def test_esc_abort_still_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        fake_backend.press_esc()
        scheduler.flush()
        assert wind_up_animator.end_calls == 1

    def test_grace_exceeded_still_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True
        manager.execute_click()
        scheduler.run_next()
        clock.advance(2.0)
        scheduler.run_next()
        assert wind_up_animator.end_calls == 1

    def test_animator_exception_does_not_strand_other_locks(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, wind_up_animator,
    ):
        """A raising animator.end() must not block transition_coordinator.end()."""
        manager = self._build_manager(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, wind_up_animator,
        )
        wind_up_animator.raise_on_end = True
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        coord_stub.end.assert_called_once()

    def test_manager_works_without_animator(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """``wind_up_animator`` is optional; older wiring must keep working."""
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        # No animator passed → no crash, and transition coord still ran.
        coord_stub.end.assert_called_once()


class TestClickWarningOverlay:
    """The warning_overlay port frames the click target during wind-up.

    Same exit-path guarantee as wind_up_animator: every terminal path
    (FIRED / ABORTED_BY_ESC / REJECTED_BY_ALLOWLIST / DRAG_GRACE_EXCEEDED)
    must call ``end()`` exactly once so the red frame never gets stuck on
    screen.
    """

    def _build(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay, bounds=(100, 200, 50, 30),
    ):
        from doro_app.core.automation.manager import AutomationManager
        return AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            warning_overlay=warning_overlay,
            bounds_provider=lambda: bounds,
            schedule=scheduler,
            clock=clock,
        )

    def test_begin_called_with_provider_bounds(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay, bounds=(10, 20, 80, 40),
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()

        assert warning_overlay.begin_calls == [(10, 20, 80, 40)]
        assert warning_overlay.end_calls == 0

    def test_fired_path_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        # >=1 because _fire_now also hides the frame *before* the class read
        # so it doesn't shield the target from WindowFromPoint (see
        # TestSelfClickingTrapAtFire). _finalize still hides idempotently.
        assert warning_overlay.end_calls >= 1

    def test_esc_abort_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        fake_backend.press_esc()
        scheduler.flush()
        assert warning_overlay.end_calls == 1

    def test_allowlist_miss_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay,
        )
        fake_backend.set_window_class("KeePassXC")
        manager.execute_click()
        scheduler.flush()
        # Allowlist miss still enters _fire_now first → pre-fire hide +
        # _finalize hide. The contract is "frame doesn't stay stuck", which
        # the idempotent end() satisfies regardless of call count.
        assert warning_overlay.end_calls >= 1

    def test_grace_exceeded_calls_end(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay,
        )
        fake_backend.set_window_class("Firefox")
        fake_backend.left_button_pressed = True
        manager.execute_click()
        scheduler.run_next()
        clock.advance(2.0)
        scheduler.run_next()
        assert warning_overlay.end_calls == 1

    def test_none_bounds_still_calls_begin(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        """When the bounds provider returns None (e.g. raw x/y move with no
        a11y id), the manager still drives the port — the adapter is the
        one that decides not to display anything."""
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            warning_overlay=warning_overlay,
            bounds_provider=lambda: None,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        assert warning_overlay.begin_calls == [None]

    def test_overlay_exception_does_not_strand_other_locks(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        """A raising overlay.end() must not block transition_coordinator.end()."""
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, warning_overlay,
        )
        warning_overlay.raise_on_end = True
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        coord_stub.end.assert_called_once()

    def test_manager_works_without_overlay(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """``warning_overlay`` is optional; older wiring must keep working."""
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        coord_stub.end.assert_called_once()


class TestClickTargetProvider:
    """Click coord sourcing: target_provider wins; foot is fallback."""

    def _build(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, target_provider, click_proximity_px=10_000,
    ):
        # Default to a very permissive proximity so this fixture exercises
        # target-vs-foot precedence without the proximity guard interfering.
        # Tests that exercise the proximity guard itself pass a smaller value.
        from doro_app.core.automation.manager import AutomationManager
        return AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            click_target_provider=target_provider,
            schedule=scheduler,
            clock=clock,
            click_proximity_px=click_proximity_px,
        )

    def test_target_overrides_foot(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        # fake_window has foot at (500, 500). Target should win.
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, target_provider=lambda: (190, 102),
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(190, 102)]

    def test_none_target_falls_back_to_foot(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, target_provider=lambda: None,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(500, 500)]

    def test_no_provider_falls_back_to_foot(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """No `click_target_provider` arg → old behaviour: click at foot."""
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(500, 500)]

    def test_target_clamped_to_screen(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        # fake_window default screen is 1920×1080. Off-screen target must clamp.
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, target_provider=lambda: (5000, -50),
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(1919, 0)]

    def test_far_target_falls_back_to_foot(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """Target beyond `click_proximity_px` from foot → click foot."""
        # foot at (500, 500), target at (1000, 1000) → ~707px away → over 300.
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock,
            target_provider=lambda: (1000, 1000),
            click_proximity_px=300,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(500, 500)]

    def test_near_target_used_within_proximity(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """Target within `click_proximity_px` of foot → click target."""
        # foot at (500, 500), target at (550, 530) → ~58px away → under 300.
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock,
            target_provider=lambda: (550, 530),
            click_proximity_px=300,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(550, 530)]

    def test_proximity_threshold_scales_with_dpr(
        self, fake_clicker, config_stub, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """The logical-px threshold is scaled by DPR before comparing
        against the physical-px distance: 450px from foot exceeds 300
        at dpr=1.0 but fits within 300×2.0 at dpr=2.0."""
        from doro_app.core.automation.fakes import FakeAutomationWindow
        window = FakeAutomationWindow(
            foot_logical=(500, 500), foot_physical=(500, 500), dpr=2.0,
        )
        manager = self._build(
            fake_clicker, config_stub, window, fake_backend, coord_stub,
            scheduler, clock,
            target_provider=lambda: (950, 500),  # 450px from foot
            click_proximity_px=300,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        assert fake_clicker.invoke_calls == [(950, 500)]

    def test_window_class_read_at_clicked_coord(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        """Allowlist check must use the actual click coord, not the foot —
        otherwise edge targets could be allowlisted via Doro's own window."""
        manager = self._build(
            fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
            scheduler, clock, target_provider=lambda: (190, 102),
        )
        # Map: foot position belongs to Firefox, target belongs to KeePass.
        fake_backend.window_class_at = {
            (500, 500): "Firefox",
            (190, 102): "KeePassXC",
        }
        manager.execute_click()
        scheduler.flush()
        # KeePassXC is not in allowlist → no click should fire.
        assert fake_clicker.invoke_calls == []


# NOTE: the legacy `TestMovementDefer` class lived here. The polling /
# 5-second-timeout defer path inside `AutomationManager` is gone — the
# orchestrator now dispatches a `MovementAction` followed by a
# `ClickAction`, and the `ActionDispatcher` only starts the click after
# the movement completion listener fires. Coverage for that sequencing
# lives in tests/core/action/test_dispatcher.py.


class TestSelfClickingTrapAtFire:
    """`read_window_class_at` and `click_left` BOTH use OS-level
    WindowFromPoint, so any Doro-owned window sitting at the click
    coordinate (Doro main with sprite-foot overlap, or the warning frame
    with WindowStaysOnTopHint) will shield the real target. Both must
    be made pass-through BEFORE the class read, not just before click."""

    def test_overlay_hidden_before_class_read(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock, warning_overlay,
    ):
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            warning_overlay=warning_overlay,
            bounds_provider=lambda: (10, 10, 5, 5),
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()

        # overlay.end() called once pre-fire AND once by _finalize → at least 1.
        assert warning_overlay.end_calls >= 1

    def test_main_window_transparent_during_class_read(
        self, fake_clicker, config_stub, fake_window, fake_backend, coord_stub,
        scheduler, clock,
    ):
        from doro_app.core.automation.manager import AutomationManager
        manager = AutomationManager(
            config_manager=config_stub,
            window=fake_window,
            input_backend=fake_backend,
            a11y_clicker=fake_clicker,
            transition_coordinator=coord_stub,
            schedule=scheduler,
            clock=clock,
        )
        fake_backend.set_window_class("Firefox")
        manager.execute_click()
        scheduler.flush()
        # set_mouse_transparent(True) must run BEFORE the click_left, and
        # restoration to False must run AFTER. The exact pre-fire ordering
        # is encoded by [True, False] in toggles.
        assert fake_window.transparent_toggles == [True, False]
