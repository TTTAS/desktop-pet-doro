"""Reaction timeline data. No Qt, no I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateStep:
    """Ask StateService to go to *key*."""

    key: str
    force: bool = False


@dataclass(frozen=True)
class WaitStep:
    """Pause *seconds* before the next step."""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ValueError("WaitStep.seconds must be >= 0")


@dataclass(frozen=True)
class SpeakStep:
    """Show a finished line. Does not call the LLM."""

    text: str


@dataclass(frozen=True)
class MoveStep:
    """Optional directional walk. Director skips it if no move port is wired."""

    direction: str
    distance: float = 0.0


@dataclass(frozen=True)
class RestoreStep:
    """Return to the committed key captured when the timeline started.

    Skipped if the director was built without a ``current_key`` port,
    or if that port returned ``None`` at play start.
    """

    force: bool = True


Step = StateStep | WaitStep | SpeakStep | MoveStep | RestoreStep


@dataclass(frozen=True)
class Timeline:
    """Named, ordered list of steps.

    Higher *priority* preempts a running timeline. Same priority also
    preempts (last start wins) so a second click replaces the first.
    """

    name: str
    steps: tuple[Step, ...]
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Timeline.name must be non-empty")
        object.__setattr__(self, "steps", tuple(self.steps))
