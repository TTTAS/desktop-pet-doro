"""Pure state data models - no UI, no I/O, no Window dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Generic, Optional, Protocol, TypeVar

# Transition wildcard constant (also defined in constants.py for UI usage)
TRANSITION_WILDCARD = "*"


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

    # Resource references (managed by Repository)
    gif_id: Optional[str] = None  # Reference to GIF, not path

    def with_changes(self, **changes: Any) -> State:
        """Return a new State with specified changes."""
        return replace(self, **changes)

    def with_visual(self, **visual_changes: Any) -> State:
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

    def with_changes(self, **changes: Any) -> MoveState:
        """Return a new MoveState with specified changes."""
        return replace(self, **changes)


# Protocol for items that can be stored in a collection
class HasKey(Protocol):
    """Protocol for objects that have a key attribute."""

    @property
    def key(self) -> str:
        """The unique identifier for this item."""
        ...


# Generic type variable for collection items
T = TypeVar("T", bound=HasKey)


class BaseCollection(Generic[T]):
    """
    Generic base class for managing collections of keyed items.

    Provides common CRUD operations for any item type that has a 'key' attribute.
    Subclasses can add domain-specific behavior.
    """

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def add(self, item: T) -> None:
        """Add or update an item in the collection."""
        self._items[item.key] = item

    def remove(self, key: str) -> bool:
        """
        Remove an item by key.

        Returns:
            True if removed, False if not found
        """
        if key not in self._items:
            return False
        del self._items[key]
        return True

    def get(self, key: str) -> Optional[T]:
        """Get an item by key."""
        return self._items.get(key)

    def all_keys(self) -> list[str]:
        """Get all item keys."""
        return list(self._items.keys())

    def all_items(self) -> dict[str, T]:
        """Get all items as a dictionary."""
        return dict(self._items)

    def __len__(self) -> int:
        """Get number of items in collection."""
        return len(self._items)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the collection."""
        return key in self._items


class StateCollection(BaseCollection[State]):
    """
    Manages a collection of states with current state tracking and protection.

    Extends BaseCollection with:
    - Current state tracking
    - Protected keys (cannot be deleted)
    - Visibility filtering
    """

    def __init__(self, states: Optional[dict[str, State]] = None) -> None:
        super().__init__()
        if states:
            self._items = states
        self._current_key: Optional[str] = None
        self._protected_keys: set[str] = {"idle"}  # Cannot be deleted

    def remove(self, key: str) -> bool:
        """
        Remove a state by key (override to check protection).

        Returns:
            True if removed, False if protected or not found
        """
        if key in self._protected_keys:
            return False

        # If removing current state, clear current
        if self._current_key == key:
            self._current_key = None

        return super().remove(key)

    def current(self) -> Optional[State]:
        """Get the currently active state."""
        if self._current_key is None:
            return None
        return self.get(self._current_key)

    def set_current(self, key: str) -> bool:
        """
        Set the current state.

        Returns:
            True if successful, False if key not found
        """
        if key not in self._items:
            return False
        self._current_key = key
        return True

    def visible_keys(self, movement_only_keys: set[str]) -> list[str]:
        """Get keys for states that should appear in UI menus."""
        return [k for k in self._items.keys() if k not in movement_only_keys]

    def protect(self, key: str) -> None:
        """Mark a state as protected (cannot be deleted)."""
        self._protected_keys.add(key)

    def is_protected(self, key: str) -> bool:
        """Check if a state is protected."""
        return key in self._protected_keys


class MoveStateCollection(BaseCollection[MoveState]):
    """
    Manages movement-specific state mappings.

    Extends BaseCollection with:
    - Case-insensitive key lookup
    - Movement-only state tracking
    - Direction-based filtering
    """

    def __init__(self) -> None:
        super().__init__()
        self._movement_only_keys: set[str] = set()

    def add(self, move_state: MoveState) -> None:
        """Add or update a movement state (case-insensitive)."""
        key = move_state.key.lower()
        # Create a modified copy with lowercase key
        normalized = MoveState(
            key=key,
            state_key=move_state.state_key,
            direction=move_state.direction,
            default_distance=move_state.default_distance,
            default_speed=move_state.default_speed,
        )
        self._items[key] = normalized
        self._movement_only_keys.add(move_state.state_key.lower())

    def remove(self, key: str) -> bool:
        """Remove a movement state (case-insensitive)."""
        key = key.lower()
        if key in self._items:
            move_state = self._items[key]
            removed_state_key = move_state.state_key.lower()

            # Remove the move_state
            result = super().remove(key)

            # Only remove from movement_only_keys if no other move_state uses this state
            still_in_use = any(
                ms.state_key.lower() == removed_state_key for ms in self._items.values()
            )
            if not still_in_use:
                self._movement_only_keys.discard(removed_state_key)

            return result
        return super().remove(key)

    def get(self, key: str) -> Optional[MoveState]:
        """Get movement state by key (case-insensitive)."""
        return self._items.get(key.lower())

    def find_by_direction(self, direction: str) -> list[MoveState]:
        """Find all movement states matching a direction."""
        direction = direction.lower()
        matches = []

        for move_state in self._items.values():
            tokens = [t.strip() for t in move_state.direction.split("|")]
            if "any" in tokens or direction in tokens:
                matches.append(move_state)

        return matches

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
class Transition:
    """
    State transition configuration.

    Represents a transition animation between two states.
    This is NOT a state itself, but a relationship between two states.
    Example: idle -> transition_gif -> happy
    """

    key: str  # Unique identifier for this transition
    from_state: str  # Starting state key
    to_state: str  # Target state key
    transition_gif_id: Optional[str] = None  # Reference to transition GIF

    def with_changes(self, **changes: Any) -> Transition:
        """Return a new Transition with specified changes."""
        return replace(self, **changes)


class TransitionCollection(BaseCollection[Transition]):
    """
    Manages state transition animations.

    Extends BaseCollection with:
    - Fast lookup by from_state -> to_state pair
    - Transition matching
    """

    def __init__(self) -> None:
        super().__init__()
        # Index for fast from->to lookup
        self._transition_map: dict[tuple[str, str], str] = {}

    def add(self, transition: Transition) -> None:
        """Add or update a transition."""
        # If overwriting an existing key, remove old index first
        old_transition = self.get(transition.key)
        if old_transition:
            old_pair = (old_transition.from_state, old_transition.to_state)
            self._transition_map.pop(old_pair, None)

        super().add(transition)
        # Update index with new transition
        self._transition_map[(transition.from_state, transition.to_state)] = transition.key

    def remove(self, key: str) -> bool:
        """Remove a transition."""
        transition = self.get(key)
        if transition:
            # Remove from index
            pair = (transition.from_state, transition.to_state)
            self._transition_map.pop(pair, None)
        return super().remove(key)

    def find_transition(self, from_state: str, to_state: str) -> Optional[Transition]:
        """
        Find a transition between two states with priority-based matching.

        Matching priority (highest to lowest):
        1. Exact match: from_state -> to_state (e.g., "idle" -> "happy")
        2. Partial wildcard:
           - from_state -> "*" (e.g., "idle" -> any state)
           - "*" -> to_state (e.g., any state -> "happy")
        3. Full wildcard: "*" -> "*" (universal transition)

        Args:
            from_state: Starting state key
            to_state: Target state key

        Returns:
            Transition if found, None otherwise

        Example:
            # Priority 1: Exact match
            find_transition("idle", "happy")  # Returns "idle" -> "happy" if exists

            # Priority 2: Partial wildcard
            find_transition("idle", "happy")  # Returns "idle" -> "*" if no exact match
            find_transition("idle", "happy")  # Returns "*" -> "happy" if no "idle" -> "*"

            # Priority 3: Universal
            find_transition("idle", "happy")  # Returns "*" -> "*" if no other matches
        """
        # Priority 1: Exact match
        key = self._transition_map.get((from_state, to_state))
        if key:
            return self.get(key)

        # Priority 2a: from_state -> "*" (from specific state to any state)
        key = self._transition_map.get((from_state, TRANSITION_WILDCARD))
        if key:
            return self.get(key)

        # Priority 2b: "*" -> to_state (from any state to specific state)
        key = self._transition_map.get((TRANSITION_WILDCARD, to_state))
        if key:
            return self.get(key)

        # Priority 3: "*" -> "*" (universal transition)
        key = self._transition_map.get((TRANSITION_WILDCARD, TRANSITION_WILDCARD))
        if key:
            return self.get(key)

        # No match found
        return None


@dataclass(frozen=True)
class GifResourceReference:
    """Reference to a GIF resource (not the file itself)."""

    resource_id: str  # Unique identifier
    display_name: str  # User-facing name
    is_primary: bool = False
