"""Pure state data models - no UI, no I/O, no Window dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Generic, Optional, Protocol, TypeVar

# Transition wildcard constant (also defined in constants.py for UI usage)
TRANSITION_WILDCARD = "*"


def normalize_state_key(key: str) -> str:
    """Canonical form for state / move-state / transition keys (strip + lowercase)."""
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


class HasKey(Protocol):
    """Protocol for objects that have a key attribute."""

    @property
    def key(self) -> str:
        """The unique identifier for this item."""
        ...


T = TypeVar("T", bound=HasKey)


def _with_normalized_key(item: T, key: str) -> T:
    """Return *item* with ``key`` rewritten when the type supports it."""
    if item.key == key:
        return item
    with_changes = getattr(item, "with_changes", None)
    if callable(with_changes):
        return with_changes(key=key)
    return item


class BaseCollection(Generic[T]):
    """
    Generic base class for managing collections of keyed items.

    Keys are stored in ``normalize_state_key`` form. Subclasses can add
    domain-specific behavior.
    """

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def add(self, item: T) -> None:
        """Add or update an item in the collection (key is normalized)."""
        key = normalize_state_key(item.key)
        self._items[key] = _with_normalized_key(item, key)

    def remove(self, key: str) -> bool:
        """
        Remove an item by key.

        Returns:
            True if removed, False if not found
        """
        key = normalize_state_key(key)
        if key not in self._items:
            return False
        del self._items[key]
        return True

    def get(self, key: str) -> Optional[T]:
        """Get an item by key (key is normalized)."""
        return self._items.get(normalize_state_key(key))

    def all_keys(self) -> list[str]:
        """Get all item keys."""
        return list(self._items.keys())

    def all_items(self) -> dict[str, T]:
        """Get all items as a new dictionary (not the internal store)."""
        return dict(self._items)

    def items(self) -> dict[str, T]:
        """Public alias for :meth:`all_items` — a shallow copy of the store."""
        return dict(self._items)

    def __len__(self) -> int:
        """Get number of items in the collection."""
        return len(self._items)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the collection."""
        return normalize_state_key(key) in self._items


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
            for state in states.values():
                self.add(state)
        self._current_key: Optional[str] = None
        self._protected_keys: set[str] = {"idle"}
        # States registered for internal (non-personality) use such as the
        # Phase 1c click action — kept playable via set_state() but hidden
        # from menus, idle picks, and the LLM-facing state list.
        self._hidden_keys: set[str] = set()

    def current_key(self) -> Optional[str]:
        """Public read of the active state key."""
        return self._current_key

    def protected_keys(self) -> frozenset[str]:
        """Public read of keys that cannot be deleted."""
        return frozenset(self._protected_keys)

    def hidden_keys(self) -> frozenset[str]:
        """Public read of keys hidden from menus / LLM lists."""
        return frozenset(self._hidden_keys)

    def remove(self, key: str) -> bool:
        """
        Remove a state by key (override to check protection).

        Returns:
            True if removed, False if protected or not found
        """
        key = normalize_state_key(key)
        if key in self._protected_keys:
            return False

        if self._current_key == key:
            self._current_key = None

        self._hidden_keys.discard(key)
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
        key = normalize_state_key(key)
        if key not in self._items:
            return False
        self._current_key = key
        return True

    def visible_keys(self, movement_only_keys: set[str]) -> list[str]:
        """Get keys for states that should appear in UI menus."""
        blocked = {normalize_state_key(k) for k in movement_only_keys}
        return [
            k
            for k in self._items.keys()
            if k not in blocked and k not in self._hidden_keys
        ]

    def protect(self, key: str) -> None:
        """Mark a state as protected (cannot be deleted)."""
        self._protected_keys.add(normalize_state_key(key))

    def is_protected(self, key: str) -> bool:
        """Check if a state is protected."""
        return normalize_state_key(key) in self._protected_keys

    def hide(self, key: str) -> None:
        """Mark a state as hidden from user-facing menus / state lists."""
        self._hidden_keys.add(normalize_state_key(key))

    def is_hidden(self, key: str) -> bool:
        """Check if a state is hidden from the visible-keys filter."""
        return normalize_state_key(key) in self._hidden_keys


class MoveStateCollection(BaseCollection[MoveState]):
    """
    Manages movement-specific state mappings.

    Extends BaseCollection with:
    - Normalized key lookup
    - Movement-only state tracking
    - Direction-based filtering
    """

    def __init__(self) -> None:
        super().__init__()
        self._movement_only_keys: set[str] = set()

    def movement_only_keys(self) -> frozenset[str]:
        """Public read of display-state keys reserved for movement."""
        return frozenset(self._movement_only_keys)

    def add(self, move_state: MoveState) -> None:
        """Add or update a movement state (keys are normalized)."""
        key = normalize_state_key(move_state.key)
        state_key = normalize_state_key(move_state.state_key)
        normalized = MoveState(
            key=key,
            state_key=state_key,
            direction=move_state.direction,
            default_distance=move_state.default_distance,
            default_speed=move_state.default_speed,
        )
        self._items[key] = normalized
        self._movement_only_keys.add(state_key)

    def remove(self, key: str) -> bool:
        """Remove a movement state (key is normalized)."""
        key = normalize_state_key(key)
        existing = self._items.get(key)
        if existing is None:
            return False

        removed_state_key = normalize_state_key(existing.state_key)
        del self._items[key]

        still_in_use = any(
            normalize_state_key(ms.state_key) == removed_state_key
            for ms in self._items.values()
        )
        if not still_in_use:
            self._movement_only_keys.discard(removed_state_key)
        return True

    def find_by_direction(self, direction: str) -> list[MoveState]:
        """Find all movement states matching a direction."""
        direction = direction.lower()
        matches = []

        for move_state in self._items.values():
            tokens = [t.strip().lower() for t in move_state.direction.split("|")]
            if "any" in tokens or direction in tokens:
                matches.append(move_state)

        return matches

    def is_movement_only(self, state_key: str) -> bool:
        """Check if a state key is reserved for movement only."""
        return normalize_state_key(state_key) in self._movement_only_keys


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

    key: str
    from_state: str
    to_state: str
    transition_gif_id: Optional[str] = None

    def with_changes(self, **changes: Any) -> Transition:
        """Return a new Transition with specified changes."""
        return replace(self, **changes)


def _normalize_transition_endpoint(value: str) -> str:
    """Normalize a from/to state, leaving the wildcard as-is after strip+lower."""
    return normalize_state_key(value)


class TransitionCollection(BaseCollection[Transition]):
    """
    Manages state transition animations.

    Extends BaseCollection with:
    - Fast lookup by from_state -> to_state pair
    - Transition matching
    """

    def __init__(self) -> None:
        super().__init__()
        self._transition_map: dict[tuple[str, str], str] = {}

    def add(self, transition: Transition) -> None:
        """Add or update a transition (endpoints are normalized)."""
        key = normalize_state_key(transition.key)
        from_state = _normalize_transition_endpoint(transition.from_state)
        to_state = _normalize_transition_endpoint(transition.to_state)
        normalized = transition.with_changes(
            key=key,
            from_state=from_state,
            to_state=to_state,
        )

        old_transition = self.get(key)
        if old_transition:
            old_pair = (old_transition.from_state, old_transition.to_state)
            self._transition_map.pop(old_pair, None)

        self._items[key] = normalized
        self._transition_map[(from_state, to_state)] = key

    def remove(self, key: str) -> bool:
        """Remove a transition."""
        transition = self.get(key)
        if transition:
            pair = (transition.from_state, transition.to_state)
            self._transition_map.pop(pair, None)
        return super().remove(key)

    def find_transition(self, from_state: str, to_state: str) -> Optional[Transition]:
        """
        Find a transition between two states with priority-based matching.

        Matching priority (highest to lowest):
        1. Exact match: from_state -> to_state
        2. Partial wildcard (from -> * , then * -> to)
        3. Full wildcard: * -> *
        """
        from_state = _normalize_transition_endpoint(from_state)
        to_state = _normalize_transition_endpoint(to_state)

        key = self._transition_map.get((from_state, to_state))
        if key:
            return self.get(key)

        key = self._transition_map.get((from_state, TRANSITION_WILDCARD))
        if key:
            return self.get(key)

        key = self._transition_map.get((TRANSITION_WILDCARD, to_state))
        if key:
            return self.get(key)

        key = self._transition_map.get((TRANSITION_WILDCARD, TRANSITION_WILDCARD))
        if key:
            return self.get(key)

        return None


@dataclass(frozen=True)
class GifResourceReference:
    """Reference to a GIF resource (not the file itself)."""

    resource_id: str
    display_name: str
    is_primary: bool = False
