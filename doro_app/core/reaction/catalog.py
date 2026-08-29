"""Named timelines. Built-ins only; no file format, no LLM authoring."""

from __future__ import annotations

from typing import Optional

from .timeline import RestoreStep, SpeakStep, StateStep, Timeline, WaitStep

# Idle must not cancel a click or an in-flight chat reaction.
PRIORITY_IDLE = 0
PRIORITY_CHAT = 10
PRIORITY_CLICK = 20


class ReactionCatalog:
    """Register and look up timelines by name."""

    def __init__(self) -> None:
        self._items: dict[str, Timeline] = {}

    def register(self, timeline: Timeline) -> None:
        self._items[timeline.name] = timeline

    def get(self, name: str) -> Optional[Timeline]:
        return self._items.get(name)

    def names(self) -> list[str]:
        return sorted(self._items)

    def register_defaults(self) -> None:
        """Short built-ins used by tests and later wiring.

        Not loaded from disk. Click flashes the protected ``click_action``
        state, waits a beat, then restores the key captured at play start.
        Idle is a no-op speak so the catalog is never empty.
        """
        self.register(
            Timeline(
                name="click",
                priority=PRIORITY_CLICK,
                steps=(
                    StateStep("click_action", force=True),
                    WaitStep(0.4),
                    RestoreStep(),
                ),
            )
        )
        self.register(
            Timeline(
                name="idle_speak",
                priority=PRIORITY_IDLE,
                steps=(SpeakStep(""),),
            )
        )


def speak_timeline(name: str, text: str, *, priority: int = PRIORITY_CHAT) -> Timeline:
    """One-line chat / companion reaction."""
    return Timeline(name=name, priority=priority, steps=(SpeakStep(text),))
