"""Tests for the screen-peek gate (proposal 7 rate-cap/permission)."""

from doro_app.core.mood.screen_peek import ScreenPeekGate

INTERVAL = 600.0


def _gate():
    return ScreenPeekGate(min_interval_s=INTERVAL)


class TestPermission:
    def test_disabled_never_peeks(self):
        g = _gate()
        assert g.should_peek(0, enabled=False, busy=False) is False

    def test_busy_never_peeks(self):
        g = _gate()
        assert g.should_peek(0, enabled=True, busy=True) is False

    def test_manual_still_needs_a11y_enabled(self):
        g = _gate()
        assert g.should_peek(0, enabled=False, busy=False, manual=True) is False

    def test_manual_still_blocked_when_busy(self):
        g = _gate()
        assert g.should_peek(0, enabled=True, busy=True, manual=True) is False


class TestRateCap:
    def test_first_auto_peek_allowed_then_capped(self):
        g = _gate()
        assert g.should_peek(0, enabled=True, busy=False) is True
        assert g.should_peek(INTERVAL - 1, enabled=True, busy=False) is False

    def test_auto_peek_allowed_after_interval(self):
        g = _gate()
        assert g.should_peek(0, enabled=True, busy=False) is True
        assert g.should_peek(INTERVAL + 1, enabled=True, busy=False) is True

    def test_manual_bypasses_rate_cap(self):
        g = _gate()
        assert g.should_peek(0, enabled=True, busy=False) is True
        # immediately after, auto would be capped but manual goes through
        assert g.should_peek(1, enabled=True, busy=False, manual=True) is True

    def test_blocked_attempt_does_not_consume_budget(self):
        g = _gate()
        # busy blocks and must NOT start the clock
        assert g.should_peek(0, enabled=True, busy=True) is False
        assert g.should_peek(1, enabled=True, busy=False) is True
