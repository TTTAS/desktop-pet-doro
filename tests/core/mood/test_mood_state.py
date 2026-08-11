"""Tests for the dual-axis mood model."""

import pytest

from doro_app.constants import (
    AFFECTION_DECAY_HALFLIFE_S,
    MOOD_DECAY_HALFLIFE_S,
    MOOD_EVENT_DELTAS,
)
from doro_app.core.mood import MoodEvent, MoodState


class TestConstruction:
    def test_defaults_are_neutral(self):
        s = MoodState()
        assert s.mood == 0.0
        assert s.affection == 0.0

    def test_out_of_range_values_are_clamped(self):
        s = MoodState(mood=5.0, affection=-3.0)
        assert s.mood == 1.0
        assert s.affection == 0.0

    def test_string_numbers_are_coerced(self):
        s = MoodState(mood="0.5", affection="0.25", last_update="123")
        assert s.mood == 0.5
        assert s.affection == 0.25
        assert s.last_update == 123.0


class TestEvents:
    def test_chat_raises_both_axes(self):
        s = MoodState(last_update=1000.0)
        s.apply_event(MoodEvent.CHAT, now=1000.0)  # no elapsed -> no decay
        dm, da = MOOD_EVENT_DELTAS["chat"]
        assert s.mood == pytest.approx(dm)
        assert s.affection == pytest.approx(da)

    def test_event_accepts_raw_string(self):
        s = MoodState(last_update=1000.0)
        s.apply_event("pet", now=1000.0)
        dm, da = MOOD_EVENT_DELTAS["pet"]
        assert s.mood == pytest.approx(dm)

    def test_ignored_lowers_axes_but_clamps_at_floor(self):
        s = MoodState(mood=0.0, affection=0.0, last_update=1000.0)
        s.apply_event(MoodEvent.IGNORED, now=1000.0)
        # mood can go negative, affection floors at 0
        assert s.mood < 0.0
        assert s.affection == 0.0

    def test_mood_never_exceeds_ceiling(self):
        s = MoodState(last_update=0.0)
        now = 1000.0
        for _ in range(100):
            s.apply_event(MoodEvent.CHAT, now=now)
            now += 0.001  # negligible decay
        assert s.mood <= 1.0
        assert s.affection <= 1.0


class TestDecay:
    # A realistic already-anchored clock; last_update=0 means "never touched".
    BASE = 1_000_000.0

    def test_mood_halves_after_one_halflife(self):
        s = MoodState(mood=0.8, affection=0.8, last_update=self.BASE)
        s.decay(now=self.BASE + MOOD_DECAY_HALFLIFE_S)
        assert s.mood == pytest.approx(0.4, abs=1e-6)

    def test_affection_barely_moves_over_a_mood_halflife(self):
        # Over 20 min, affection (1-day half-life) should lose <2%.
        s = MoodState(mood=0.8, affection=0.8, last_update=self.BASE)
        s.decay(now=self.BASE + MOOD_DECAY_HALFLIFE_S)
        assert s.affection == pytest.approx(0.8, abs=0.02)

    def test_affection_halves_after_its_own_halflife(self):
        s = MoodState(affection=0.6, last_update=self.BASE)
        s.decay(now=self.BASE + AFFECTION_DECAY_HALFLIFE_S)
        assert s.affection == pytest.approx(0.3, abs=1e-6)

    def test_first_touch_only_anchors_clock(self):
        s = MoodState(mood=0.8, last_update=0.0)
        s.decay(now=5000.0)
        assert s.mood == 0.8  # nothing decayed on the first anchor
        assert s.last_update == 5000.0

    def test_backwards_clock_does_not_amplify(self):
        s = MoodState(mood=0.5, last_update=1000.0)
        s.decay(now=500.0)  # clock went backwards
        assert s.mood == pytest.approx(0.5)


class TestLabels:
    def test_mood_bands(self):
        assert MoodState(mood=0.9).mood_label() == "很開心"
        assert MoodState(mood=0.0).mood_label() == "普普通通"
        assert MoodState(mood=-0.9).mood_label() == "鬧脾氣、很沮喪"

    def test_affection_bands(self):
        assert "孤單" in MoodState(affection=0.0).affection_label()
        assert "黏人" in MoodState(affection=0.9).affection_label()

    def test_describe_contains_both_axes(self):
        block = MoodState(mood=0.9, affection=0.9, last_update=1.0).describe(now=1.0)
        assert "[Doro 心情]" in block
        assert "很開心" in block
        assert "黏人" in block


class TestPersistence:
    def test_round_trip(self):
        s = MoodState(mood=0.3, affection=0.7, last_update=12345.0)
        restored = MoodState.from_dict(s.to_dict())
        assert restored.mood == pytest.approx(0.3)
        assert restored.affection == pytest.approx(0.7)
        assert restored.last_update == 12345.0

    def test_from_none_gives_neutral(self):
        s = MoodState.from_dict(None)
        assert s.mood == 0.0 and s.affection == 0.0

    def test_from_garbage_is_tolerated(self):
        s = MoodState.from_dict({"mood": "oops", "affection": None})
        assert s.mood == 0.0
        assert s.affection == 0.0
