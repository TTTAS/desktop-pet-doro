"""Tests for the pure event detector (state-mirror reactions)."""

from doro_app.constants import (
    APP_SWITCH_REACT_COOLDOWN_S,
    APP_SWITCH_SETTLE_S,
    LONG_SITTING_THRESHOLD_S,
    SITTING_BREAK_S,
)
from doro_app.core.mood.event_detector import EventDetector, ReactionEvent

ACTIVE = 0.0          # idle seconds < break -> user is present
AWAY = SITTING_BREAK_S + 1
DAY = "2026-08-11"
NOON = 12             # an hour with no time-of-day greeting


def _poll(det, now, cls=None, idle=ACTIVE, hour=NOON, date=DAY):
    return det.poll(now, cls, idle, hour, date)


class TestAppSwitchSettle:
    def test_new_app_settles_only_after_settle_window(self):
        det = EventDetector()
        assert _poll(det, 0, cls="Code").settled_app is None  # candidate starts
        assert _poll(det, 5, cls="Code").settled_app is None  # not yet settled
        r = _poll(det, APP_SWITCH_SETTLE_S + 1, cls="Code")
        assert r.settled_app == "Code"

    def test_flapping_app_never_settles(self):
        det = EventDetector()
        for t in range(0, 100, 3):
            cls = "Code" if (t // 3) % 2 == 0 else "Chrome"
            assert _poll(det, t, cls=cls).settled_app is None

    def test_none_class_is_ignored(self):
        det = EventDetector()
        _poll(det, 0, cls="Code")
        # Doro's own window (None) must not reset the candidate clock
        assert _poll(det, 5, cls=None).settled_app is None
        assert _poll(det, APP_SWITCH_SETTLE_S + 1, cls="Code").settled_app == "Code"

    def test_settle_fires_app_switch_reaction(self):
        det = EventDetector()
        _poll(det, 0, cls="Code")
        r = _poll(det, APP_SWITCH_SETTLE_S + 1, cls="Code")
        assert r.reaction is ReactionEvent.APP_SWITCH

    def test_app_switch_reaction_respects_cooldown(self):
        det = EventDetector()
        # first switch settles + reacts
        _poll(det, 0, cls="Code")
        assert _poll(det, 11, cls="Code").reaction is ReactionEvent.APP_SWITCH
        # switch to a new app shortly after: settles but reaction suppressed
        _poll(det, 20, cls="Chrome")
        r = _poll(det, 31, cls="Chrome")
        assert r.settled_app == "Chrome"
        assert r.reaction is None
        # after the cooldown, a new settle reacts again
        base = 31 + APP_SWITCH_REACT_COOLDOWN_S
        _poll(det, base, cls="Slack")
        assert _poll(det, base + 11, cls="Slack").reaction is ReactionEvent.APP_SWITCH


class TestLongSitting:
    def test_fires_after_threshold(self):
        det = EventDetector()
        _poll(det, 0, idle=ACTIVE)  # active run starts
        assert _poll(det, LONG_SITTING_THRESHOLD_S - 1, idle=ACTIVE).reaction is None
        r = _poll(det, LONG_SITTING_THRESHOLD_S + 1, idle=ACTIVE)
        assert r.reaction is ReactionEvent.LONG_SITTING

    def test_fires_only_once_per_sitting(self):
        det = EventDetector()
        _poll(det, 0, idle=ACTIVE)
        assert _poll(det, LONG_SITTING_THRESHOLD_S + 1, idle=ACTIVE).reaction is ReactionEvent.LONG_SITTING
        assert _poll(det, LONG_SITTING_THRESHOLD_S + 100, idle=ACTIVE).reaction is None

    def test_break_resets_the_timer(self):
        det = EventDetector()
        _poll(det, 0, idle=ACTIVE)
        _poll(det, LONG_SITTING_THRESHOLD_S + 1, idle=ACTIVE)  # fires
        _poll(det, LONG_SITTING_THRESHOLD_S + 2, idle=AWAY)    # took a break
        # new run starts here
        start = LONG_SITTING_THRESHOLD_S + 10
        _poll(det, start, idle=ACTIVE)
        assert _poll(det, start + LONG_SITTING_THRESHOLD_S + 1, idle=ACTIVE).reaction is ReactionEvent.LONG_SITTING


class TestTimeOfDay:
    def test_late_night_fires_once_when_present(self):
        det = EventDetector()
        assert _poll(det, 0, hour=1, idle=ACTIVE).reaction is ReactionEvent.LATE_NIGHT
        assert _poll(det, 60, hour=2, idle=ACTIVE).reaction is None  # same day

    def test_morning_fires_once(self):
        det = EventDetector()
        assert _poll(det, 0, hour=7, idle=ACTIVE).reaction is ReactionEvent.MORNING
        assert _poll(det, 60, hour=8, idle=ACTIVE).reaction is None

    def test_not_fired_when_user_away(self):
        det = EventDetector()
        assert _poll(det, 0, hour=1, idle=AWAY).reaction is None

    def test_new_day_fires_again(self):
        det = EventDetector()
        assert _poll(det, 0, hour=7, date="2026-08-11", idle=ACTIVE).reaction is ReactionEvent.MORNING
        assert _poll(det, 90000, hour=7, date="2026-08-12", idle=ACTIVE).reaction is ReactionEvent.MORNING


class TestPriority:
    def test_time_of_day_beats_app_switch(self):
        det = EventDetector()
        # Start at noon so late-night doesn't fire early; the app becomes a
        # candidate now and settles on the next poll — the same poll where
        # we flip to late-night, making both eligible at once.
        _poll(det, 0, cls="Code", hour=12, idle=ACTIVE)
        r = _poll(det, APP_SWITCH_SETTLE_S + 1, cls="Code", hour=1, idle=ACTIVE)
        assert r.reaction is ReactionEvent.LATE_NIGHT
        assert r.settled_app == "Code"

        # app-switch cooldown must NOT have been consumed: a fresh app that
        # settles later still reacts.
        _poll(det, 100, cls="Chrome", hour=1, idle=ACTIVE)
        assert _poll(det, 100 + APP_SWITCH_SETTLE_S + 1, cls="Chrome",
                     hour=1, idle=ACTIVE).reaction is ReactionEvent.APP_SWITCH
