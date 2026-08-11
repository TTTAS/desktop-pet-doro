"""Dual-axis emotion model for Doro.

Pure domain logic — no Qt, no I/O, no wall-clock reads except through the
injectable ``now`` parameter. That keeps the whole thing deterministically
testable and cheap enough to update on every interaction (the measured
system burden is negligible, and this adds only a couple of float ops).

Two axes:
  • ``mood``      — the current feeling, ``[-1, 1]`` (0 = neutral). Swings on
                    events, then decays back toward neutral over ~20 min.
  • ``affection`` — the long-term bond, ``[0, 1]`` (0 = distant/lonely).
                    Grows with interaction, fades slowly (~1 day half-life)
                    when Doro is ignored. This is what makes her feel like
                    someone you're *raising* rather than a moving sprite.

``mood`` reacts; ``affection`` remembers.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum

from ...constants import (
    AFFECTION_DECAY_HALFLIFE_S,
    AFFECTION_MAX,
    AFFECTION_MIN,
    MOOD_DECAY_HALFLIFE_S,
    MOOD_EVENT_DELTAS,
    MOOD_MAX,
    MOOD_MIN,
)


class MoodEvent(str, Enum):
    """A thing that happened, mapped to a mood/affection nudge.

    String-valued so it round-trips through config/logs and indexes
    directly into ``MOOD_EVENT_DELTAS``.
    """

    CHAT = "chat"
    PET = "pet"
    PLAY = "play"
    RETURN = "return"
    IGNORED = "ignored"


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _decay_factor(elapsed: float, half_life: float) -> float:
    """Fraction of a value that *remains* after ``elapsed`` seconds.

    Exponential decay: ``0.5 ** (elapsed / half_life)``. Guards against a
    non-positive elapsed (clock jitter / same-instant calls → no decay) and
    a non-positive half-life (treated as "no decay").
    """

    if elapsed <= 0 or half_life <= 0:
        return 1.0
    return math.pow(0.5, elapsed / half_life)


@dataclass
class MoodState:
    """Doro's current emotional state on the two axes.

    ``last_update`` is a wall-clock timestamp (``time.time()``) so decay
    keeps running across app restarts — a Doro left alone overnight should
    wake up a little lonelier.
    """

    mood: float = 0.0
    affection: float = 0.0
    last_update: float = 0.0

    def __post_init__(self) -> None:
        self.mood = _clamp(float(self.mood), MOOD_MIN, MOOD_MAX)
        self.affection = _clamp(float(self.affection), AFFECTION_MIN, AFFECTION_MAX)
        self.last_update = float(self.last_update)

    # ── evolution ────────────────────────────────────────────────────────

    def decay(self, now: float | None = None) -> None:
        """Age both axes toward their resting points given elapsed time.

        Mood decays toward 0 (neutral); affection decays toward 0 (distant).
        Idempotent within the same instant and safe to call as often as you
        like — it advances ``last_update`` each time.
        """

        now = time.time() if now is None else now
        if self.last_update <= 0:
            # First ever touch: anchor the clock, nothing to decay yet.
            self.last_update = now
            return
        elapsed = now - self.last_update
        self.mood *= _decay_factor(elapsed, MOOD_DECAY_HALFLIFE_S)
        self.affection *= _decay_factor(elapsed, AFFECTION_DECAY_HALFLIFE_S)
        self.last_update = now

    def apply_event(self, event: MoodEvent, now: float | None = None) -> None:
        """Decay to ``now`` then apply the event's nudge, clamping to range."""

        now = time.time() if now is None else now
        self.decay(now)
        mood_delta, affection_delta = MOOD_EVENT_DELTAS[MoodEvent(event).value]
        self.mood = _clamp(self.mood + mood_delta, MOOD_MIN, MOOD_MAX)
        self.affection = _clamp(
            self.affection + affection_delta, AFFECTION_MIN, AFFECTION_MAX
        )

    # ── description (for prompt injection & UI) ──────────────────────────

    def mood_label(self) -> str:
        """Chinese descriptor of the current mood band."""
        m = self.mood
        if m >= 0.5:
            return "很開心"
        if m >= 0.15:
            return "心情不錯"
        if m > -0.15:
            return "普普通通"
        if m > -0.5:
            return "有點低落"
        return "鬧脾氣、很沮喪"

    def affection_label(self) -> str:
        """Chinese descriptor of the current affection band."""
        a = self.affection
        if a >= 0.75:
            return "跟人超級親密、很黏人"
        if a >= 0.4:
            return "跟人很熟、很喜歡人"
        if a >= 0.15:
            return "還在跟人慢慢熟"
        return "有點生疏、覺得孤單"

    def describe(self, now: float | None = None) -> str:
        """A prompt-ready block telling the LLM how to colour its voice.

        Decays first so the description reflects *now*, not the last event.
        """

        self.decay(now)
        return (
            "[Doro 心情]\n"
            f"心情：{self.mood_label()}\n"
            f"親密度：{self.affection_label()}\n"
            "（讓語氣自然反映這個心情和親密度，但不要直接照唸這些字。）"
        )

    # ── persistence ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float]:
        return {
            "mood": self.mood,
            "affection": self.affection,
            "last_update": self.last_update,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "MoodState":
        """Rebuild from persisted data, tolerating missing/garbage fields."""
        if not isinstance(data, dict):
            return cls()

        def _num(key: str, default: float) -> float:
            try:
                return float(data.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            mood=_num("mood", 0.0),
            affection=_num("affection", 0.0),
            last_update=_num("last_update", 0.0),
        )
