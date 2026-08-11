"""Tests for the pre-written companion line library."""

import json
from pathlib import Path

from doro_app.core.mood import MoodState
from doro_app.core.mood.speech import CompanionLines
from doro_app.utils.paths import COMPANION_LINES_PATH


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "lines.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


class TestLoading:
    def test_shipped_file_loads_expected_buckets(self):
        lines = CompanionLines(COMPANION_LINES_PATH)
        for key in ("idle_happy", "idle_neutral", "idle_low", "lonely",
                    "long_sitting", "late_night", "morning", "app_switch"):
            assert lines.has(key), f"missing bucket {key}"

    def test_comment_and_nonlists_are_skipped(self, tmp_path):
        p = _write(tmp_path, {"_comment": "x", "greet": ["hi"], "bad": 5})
        lines = CompanionLines(p)
        assert lines.has("greet")
        assert not lines.has("_comment")
        assert not lines.has("bad")

    def test_blank_lines_are_dropped(self, tmp_path):
        p = _write(tmp_path, {"greet": ["  ", "", "hi"]})
        lines = CompanionLines(p)
        assert lines.pick("greet") == "hi"

    def test_missing_file_is_empty(self, tmp_path):
        lines = CompanionLines(tmp_path / "nope.json")
        assert lines.pick("greet") is None

    def test_bad_json_is_empty(self, tmp_path):
        p = tmp_path / "lines.json"
        p.write_text("{not json", encoding="utf-8")
        assert CompanionLines(p).pick("greet") is None


class TestPick:
    def test_pick_returns_member_of_category(self, tmp_path):
        p = _write(tmp_path, {"greet": ["a", "b", "c"]})
        lines = CompanionLines(p)
        assert lines.pick("greet") in {"a", "b", "c"}

    def test_pick_falls_through_to_next_key(self, tmp_path):
        p = _write(tmp_path, {"b": ["fromB"]})
        lines = CompanionLines(p)
        assert lines.pick("a", "b") == "fromB"

    def test_pick_all_missing_is_none(self, tmp_path):
        lines = CompanionLines(_write(tmp_path, {"a": ["x"]}))
        assert lines.pick("nope", "nada") is None


class TestPickIdle:
    def _lib(self, tmp_path):
        return CompanionLines(_write(tmp_path, {
            "idle_happy": ["happy"],
            "idle_neutral": ["neutral"],
            "idle_low": ["low"],
            "lonely": ["lonely"],
        }))

    def test_low_affection_is_lonely_regardless_of_mood(self, tmp_path):
        lib = self._lib(tmp_path)
        assert lib.pick_idle(MoodState(mood=0.9, affection=0.05)) == "lonely"

    def test_happy_when_mood_high_and_bonded(self, tmp_path):
        lib = self._lib(tmp_path)
        assert lib.pick_idle(MoodState(mood=0.6, affection=0.8)) == "happy"

    def test_low_when_mood_negative_and_bonded(self, tmp_path):
        lib = self._lib(tmp_path)
        assert lib.pick_idle(MoodState(mood=-0.5, affection=0.8)) == "low"

    def test_neutral_in_between(self, tmp_path):
        lib = self._lib(tmp_path)
        assert lib.pick_idle(MoodState(mood=0.0, affection=0.8)) == "neutral"

    def test_none_mood_defaults_neutral(self, tmp_path):
        lib = self._lib(tmp_path)
        assert lib.pick_idle(None) == "neutral"

    def test_falls_back_to_neutral_when_band_empty(self, tmp_path):
        lib = CompanionLines(_write(tmp_path, {"idle_neutral": ["only"]}))
        # mood high would want idle_happy (absent) -> falls to idle_neutral
        assert lib.pick_idle(MoodState(mood=0.9, affection=0.8)) == "only"
