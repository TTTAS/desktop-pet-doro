"""Pure event detection for Doro's state-mirror reactions.

Given periodic observations of the world (foreground app, how long you've
been idle, the local hour/date) this decides *when* Doro should react — and
to what — applying settle windows and cooldowns so she feels attentive, not
spammy. No Qt, no clock reads, no I/O: everything comes in through
:meth:`poll`, so the whole policy is deterministically testable.

The Qt wrapper (:mod:`event_reactor`) supplies the observations on a timer
and turns the returned events into bubble lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from ...constants import (
    APP_SWITCH_REACT_COOLDOWN_S,
    APP_SWITCH_SETTLE_S,
    LATE_NIGHT_HOURS,
    LONG_SITTING_THRESHOLD_S,
    MORNING_HOURS,
    SITTING_BREAK_S,
)


class ReactionEvent(Enum):
    """A reason for Doro to say something, mapped to a companion-line key."""

    APP_SWITCH = auto()
    LONG_SITTING = auto()
    LATE_NIGHT = auto()
    MORNING = auto()


# ReactionEvent -> companion_lines.json bucket
REACTION_LINE_KEYS = {
    ReactionEvent.APP_SWITCH: "app_switch",
    ReactionEvent.LONG_SITTING: "long_sitting",
    ReactionEvent.LATE_NIGHT: "late_night",
    ReactionEvent.MORNING: "morning",
}


@dataclass
class PollResult:
    """Outcome of one poll.

    ``settled_app`` is set on the tick a *new* foreground app finishes
    settling (used by the optional screen-read, regardless of reaction
    cooldowns). ``reaction`` is the (at most one) canned reaction to fire.
    """

    settled_app: Optional[str] = None
    reaction: Optional[ReactionEvent] = None


class EventDetector:
    """Tracks just enough history to fire events with sane cooldowns."""

    def __init__(self) -> None:
        # app-switch settle tracking
        self._stable_class: Optional[str] = None
        self._candidate: Optional[str] = None
        self._candidate_since: float = 0.0
        self._last_app_react: float = float("-inf")
        # long-sitting tracking
        self._active_since: Optional[float] = None
        self._sitting_fired: bool = False
        # once-per-day greetings: event name -> date string last fired
        self._daily: dict[str, str] = {}

    def poll(
        self,
        now: float,
        foreground_class: Optional[str],
        idle_seconds: float,
        hour: int,
        date: str,
    ) -> PollResult:
        settled = self._update_app_settle(now, foreground_class)
        reaction = self._pick_reaction(now, idle_seconds, hour, date, settled)
        return PollResult(settled_app=settled, reaction=reaction)

    # ── app switch settle ────────────────────────────────────────────────

    def _update_app_settle(
        self, now: float, cls: Optional[str]
    ) -> Optional[str]:
        """Return the class name on the tick a new app finishes settling.

        ``cls`` is the current *external* foreground class (None when it's
        Doro's own window or unreadable — those are ignored so they never
        reset the candidate).
        """
        if not cls:
            return None
        if cls == self._stable_class:
            # already the stable app; make sure no stale candidate lingers
            self._candidate = None
            return None
        if cls != self._candidate:
            # a new contender — start its settle clock
            self._candidate = cls
            self._candidate_since = now
            return None
        # same candidate still in front — has it settled?
        if now - self._candidate_since >= APP_SWITCH_SETTLE_S:
            self._stable_class = cls
            self._candidate = None
            return cls
        return None

    # ── reaction selection ───────────────────────────────────────────────

    def _pick_reaction(
        self,
        now: float,
        idle_seconds: float,
        hour: int,
        date: str,
        settled_app: Optional[str],
    ) -> Optional[ReactionEvent]:
        active = idle_seconds < SITTING_BREAK_S

        # Maintain the continuous-active run for long-sitting.
        if not active:
            self._active_since = None
            self._sitting_fired = False
        elif self._active_since is None:
            self._active_since = now

        # Greetings only make sense when you're actually around.
        if active and hour in LATE_NIGHT_HOURS and self._daily.get("late_night") != date:
            self._daily["late_night"] = date
            return ReactionEvent.LATE_NIGHT
        if active and hour in MORNING_HOURS and self._daily.get("morning") != date:
            self._daily["morning"] = date
            return ReactionEvent.MORNING

        # Been glued to the chair?
        if (
            active
            and self._active_since is not None
            and not self._sitting_fired
            and now - self._active_since >= LONG_SITTING_THRESHOLD_S
        ):
            self._sitting_fired = True
            return ReactionEvent.LONG_SITTING

        # A freshly-settled app, rate-limited.
        if (
            settled_app is not None
            and now - self._last_app_react >= APP_SWITCH_REACT_COOLDOWN_S
        ):
            self._last_app_react = now
            return ReactionEvent.APP_SWITCH

        return None
