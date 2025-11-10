"""Pure state data models - no UI, no I/O, no Window dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional


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

    def with_changes(self, **changes) -> VisualConfig:
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

    # Resource references (managed by Repository)
    primary_gif_id: Optional[str] = None  # Reference to GIF, not path
    variant_gif_ids: tuple[str, ...] = field(default_factory=tuple)

    def with_changes(self, **changes) -> State:
        """Return a new State with specified changes."""
        return replace(self, **changes)

    def with_visual(self, **visual_changes) -> State:
        """Return a new State with modified visual config."""
        new_visual = self.visual.with_changes(**visual_changes)
        return replace(self, visual=new_visual)


@dataclass(frozen=True)
class MoveState:
    """
    Movement-specific state configuration.

    Associates a movement action with a display state.
    """

    key: str
    state_key: str  # Reference to the State to use
    direction: str = "any"  # "left", "right", "up|down", etc.
    default_distance: Optional[float] = None
    default_speed: str = "med"  # "slow", "med", "fast"

    def with_changes(self, **changes) -> MoveState:
        """Return a new MoveState with specified changes."""
        return replace(self, **changes)


class StateCollection:
    """
    Manages a collection of states.

    Responsibilities:
    - Store states by key
    - Track current state
    - Validate state transitions
    - NO file I/O
    - NO UI logic
    """

    def __init__(self, states: Optional[dict[str, State]] = None):
        self._states: dict[str, State] = states or {}
        self._current_key: Optional[str] = None
        self._protected_keys: set[str] = {"idle"}  # Cannot be deleted

    def add(self, state: State) -> None:
        """Add or update a state."""
        self._states[state.key] = state

    def remove(self, key: str) -> bool:
        """
        Remove a state by key.

        Returns:
            True if removed, False if protected or not found
        """
        if key in self._protected_keys or key not in self._states:
            return False

        # If removing current state, clear current
        if self._current_key == key:
            self._current_key = None

        del self._states[key]
        return True

    def get(self, key: str) -> Optional[State]:
        """Get state by key."""
        return self._states.get(key)

    def current(self) -> Optional[State]:
        """Get the current state."""
        if self._current_key is None:
            return None
        return self._states.get(self._current_key)

    def set_current(self, key: str) -> bool:
        """
        Set current state.

        Returns:
            True if successful, False if key not found
        """
        if key not in self._states:
            return False
        self._current_key = key
        return True

    def all_keys(self) -> list[str]:
        """Get all state keys."""
        return list(self._states.keys())

    def visible_keys(self, movement_only_keys: set[str]) -> list[str]:
        """Get keys for states that should appear in UI menus."""
        return [k for k in self._states.keys() if k not in movement_only_keys]

    def protect(self, key: str) -> None:
        """Mark a state as protected (cannot be deleted)."""
        self._protected_keys.add(key)

    def is_protected(self, key: str) -> bool:
        """Check if a state is protected."""
        return key in self._protected_keys


class MoveStateCollection:
    """
    Manages movement-specific state mappings.

    Maps movement actions (e.g., "walk_left") to display states.
    """

    def __init__(self):
        self._move_states: dict[str, MoveState] = {}
        self._movement_only_keys: set[str] = set()

    def add(self, move_state: MoveState) -> None:
        """Add or update a movement state."""
        key = move_state.key.lower()
        self._move_states[key] = move_state
        self._movement_only_keys.add(move_state.state_key.lower())

    def remove(self, key: str) -> bool:
        """Remove a movement state."""
        key = key.lower()
        if key not in self._move_states:
            return False

        move_state = self._move_states[key]
        self._movement_only_keys.discard(move_state.state_key.lower())
        del self._move_states[key]
        return True

    def get(self, key: str) -> Optional[MoveState]:
        """Get movement state by key."""
        return self._move_states.get(key.lower())

    def find_by_direction(self, direction: str) -> list[MoveState]:
        """Find all movement states matching a direction."""
        direction = direction.lower()
        matches = []

        for move_state in self._move_states.values():
            tokens = [t.strip() for t in move_state.direction.split("|")]
            if "any" in tokens or direction in tokens:
                matches.append(move_state)

        return matches

    def all_keys(self) -> list[str]:
        """Get all movement state keys."""
        return list(self._move_states.keys())

    def is_movement_only(self, state_key: str) -> bool:
        """Check if a state key is reserved for movement only."""
        return state_key.lower() in self._movement_only_keys


@dataclass(frozen=True)
class StateChangeEvent:
    """Event emitted when state changes."""

    old_key: Optional[str]
    new_key: str
    new_state: State


@dataclass(frozen=True)
class GifResourceReference:
    """Reference to a GIF resource (not the file itself)."""

    resource_id: str  # Unique identifier
    display_name: str  # User-facing name
    is_primary: bool = False
