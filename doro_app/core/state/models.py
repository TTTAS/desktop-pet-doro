"""Pure state data models - no UI, no I/O, no Window dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Generic, Optional, Protocol, TypeVar

# Transition wildcard constant (also defined in constants.py for UI usage)
TRANSITION_WILDCARD = "*"


def normalize_state_key(key: str) -> str:
    """Canonical form for state / move-state keys (strip + lowercase)."""
    return key.strip().lower()


@dataclass(frozen=True)
class VisualConfig:
    """Visual appearance settings for a state (immutable)."""

    bob_amplitude: float = 6.0
    scale_amplitude: float = 0.04
    gradient_top: str = "#FFFFFFFF"
    gradient_mid: str = "#FF9BE3FF"
    gradient_bottom: str = "#FF6CC1F0"
    cheeks_alpha: float = 204
    blush_color: str = "#FFC0C0"
    eye_color: str = "#222222"
    bubble_visible: bool = True
    bubble_alpha: float = 170

    def with_changes(self, **changes: Any) -> VisualConfig:
        """Return a new VisualConfig with specified changes."""
        return replace(self, **changes)


@dataclass(frozen=True)
class State:
    """
    Represents a single state (e.g., 'idle', 'happy').

    Immutable by design - use with_changes() to create modified copies.
    Does NOT contain file paths or I/O logic.
    """

    key: str
    label: str
    name_tag: str = "doro"
    visual: VisualConfig = field(default_factory=VisualConfig)

    gif_id: Optional[str] = None

    def with_changes(self, **changes: Any) -> State:
        """Return a new State with specified changes."""
        return replace(self, **changes)

    def with_visual(self, **visual_changes: Any) -> State:
        """Return a new State with modified visual config."""
        new_visual = self.visual.with_changes(**visual_changes)
        return replace(self, visual=new_visual)
