"""
State management service - orchestrates state operations without UI coupling.

This is the NEW StateManager. The old one is 1565 lines of chaos.
This one has clear responsibilities and no Window dependency.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable, Optional

from ...utils.logger import get_logger
from .models import MoveState, MoveStateCollection, State, StateChangeEvent, StateCollection, TransitionState, TransitionStateCollection, VisualConfig
from .repository import GifRepository, MoveStateRepository, StateListWriter, StateRepository, TransitionStateRepository

logger = get_logger(__name__)


class StateService:
    """
    Manages application state lifecycle.

    Responsibilities:
    - Coordinate state changes
    - Manage state collections
    - Emit events for UI to respond to
    - Delegate I/O to repositories

    Does NOT:
    - Know about Window or Qt
    - Perform file I/O directly
    - Show dialogs or UI
    """

    def __init__(
        self,
        state_repo: StateRepository,
        move_repo: MoveStateRepository,
        gif_repo: GifRepository,
        state_list_path: Path,
        transition_repo: Optional[TransitionStateRepository] = None,
    ):
        # Private - encapsulated repositories
        self._state_repo = state_repo
        self._move_repo = move_repo
        self._gif_repo = gif_repo
        self._transition_repo = transition_repo
        self._state_list_writer = StateListWriter(state_list_path)

        # Private - encapsulated collections
        self._states = StateCollection()
        self._move_states = MoveStateCollection()
        self._transitions = TransitionStateCollection()

        # Transition protection flag
        self._is_transitioning: bool = False

        # Event callbacks (public - set by Window or controller)
        self.on_state_changed: Optional[Callable[[StateChangeEvent], None]] = None
        self.on_states_modified: Optional[Callable[[], None]] = None

    # ═══════════════════════════════════════════════════════════
    # Public API - GIF Operations (Encapsulated)
    # ═══════════════════════════════════════════════════════════

    def get_gif_path(self, state_key: str) -> Optional[Path]:
        """
        Get the file path for a state's GIF.

        Args:
            state_key: State key

        Returns:
            Absolute path to GIF file or None if not found
        """
        state = self._states.get(state_key)
        if not state or not state.gif_id:
            return None
        return self._gif_repo.get_path(state.gif_id)

    def get_gif_path_by_id(self, gif_id: str) -> Optional[Path]:
        """
        Get the file path for a GIF resource ID.

        Args:
            gif_id: GIF resource ID

        Returns:
            Absolute path to GIF file or None if not found
        """
        return self._gif_repo.get_path(gif_id)

    def store_gif(self, source_path: Path, state_key: str) -> Optional[str]:
        """
        Store a GIF file for a state.

        Args:
            source_path: Source GIF file path
            state_key: State key this GIF belongs to

        Returns:
            Resource ID or None if failed
        """
        return self._gif_repo.store_gif(source_path, state_key)

    def delete_gif(self, gif_id: str) -> bool:
        """
        Delete a GIF by resource ID.

        Args:
            gif_id: GIF resource ID

        Returns:
            True if deleted, False otherwise
        """
        return self._gif_repo.delete(gif_id)

    def get_state_storage_path(self, state_key: str) -> Path:
        """
        Get the expected storage path for a state's GIF.

        Args:
            state_key: State key

        Returns:
            Path where the state's GIF should be stored
        """
        return self._gif_repo.get_state_storage_path(state_key)

    def get_move_storage_path(self, move_key: str) -> Path:
        """
        Get the expected storage path for a movement action's GIF.

        Args:
            move_key: Movement key (e.g., "walking")

        Returns:
            Path where the move GIF should be stored
        """
        return self._gif_repo.get_move_storage_path(move_key)

    def sanitize_state_key(self, key: str) -> str:
        """
        Sanitize a key for safe use in filenames.

        Args:
            key: Raw key string

        Returns:
            Sanitized filename-safe string
        """
        return self._gif_repo.sanitize_filename(key)

    # ═══════════════════════════════════════════════════════════
    # Public API - Query Methods
    # ═══════════════════════════════════════════════════════════

    def get_state(self, key: str) -> Optional[State]:
        """Get a state by key."""
        return self._states.get(key)

    def has_state(self, key: str) -> bool:
        """Check if a state exists."""
        return self._states.get(key) is not None

    def get_current_state(self) -> Optional[State]:
        """Get the currently active state."""
        return self._states.current()

    def get_current_state_key(self) -> Optional[str]:
        """Get the key of the currently active state."""
        return self._states._current_key

    def visible_state_keys(self) -> list[str]:
        """Get all state keys that should be visible in UI."""
        return self._states.visible_keys(self._move_states._movement_only_keys)

    def all_state_keys(self) -> list[str]:
        """Get all state keys."""
        return self._states.all_keys()

    def is_state_protected(self, key: str) -> bool:
        """Check if a state is protected from deletion."""
        return self._states.is_protected(key)

    def is_movement_only_state(self, key: str) -> bool:
        """Check if a state key is reserved for movement only."""
        return self._move_states.is_movement_only(key)

    def get_move_state(self, key: str) -> Optional[MoveState]:
        """Get a movement state by key."""
        return self._move_states.get(key)

    def all_move_state_keys(self) -> list[str]:
        """Get all movement state keys."""
        return self._move_states.all_keys()

    def find_move_states_by_direction(self, direction_slug: str) -> list[MoveState]:
        """Find all movement states that support the given direction."""
        return self._move_states.find_by_direction(direction_slug)

    def get_default_movement_state(self) -> Optional[str]:
        """Get the default movement state key (usually 'walking')."""
        # Try to find 'walking' state
        if self.get_state("walking"):
            return "walking"
        # Fall back to any move state with direction="any"
        for move_state in self._move_states.find_by_direction("any"):
            if self.get_state(move_state.state_key):
                return move_state.state_key
        return None

    def find_state_by_label(self, label_query: str) -> Optional[str]:
        """Find a state key by searching labels (case-insensitive)."""
        query_lower = label_query.lower().strip()
        for key in self._states.all_keys():
            state = self._states.get(key)
            if state and state.label.lower() == query_lower:
                return key
        return None

    # ═══════════════════════════════════════════════════════════
    # Public API - Transition Query Methods
    # ═══════════════════════════════════════════════════════════

    def get_transition(self, key: str) -> Optional[TransitionState]:
        """Get a transition by key."""
        return self._transitions.get(key)

    def all_transition_keys(self) -> list[str]:
        """Get all transition keys."""
        return self._transitions.all_keys()

    def find_transition(self, from_state: str, to_state: str) -> Optional[TransitionState]:
        """Find a transition between two states."""
        return self._transitions.find_transition(from_state, to_state)

    # ═══════════════════════════════════════════════════════════
    # Public API - State Modification
    # ═══════════════════════════════════════════════════════════

    def update_state(self, key: str, **changes: Any) -> bool:
        """
        Update any fields of a state.

        Returns:
            True if successful, False if state not found
        """
        state = self._states.get(key)
        if not state:
            return False

        updated = state.with_changes(**changes)
        self._states.add(updated)
        self._save_states()
        self._emit_states_modified()
        return True

    def update_visual_config(self, key: str, **visual_changes: Any) -> bool:
        """
        Update visual configuration for a state.

        Returns:
            True if successful, False if state not found
        """
        state = self._states.get(key)
        if not state:
            return False

        updated = state.with_visual(**visual_changes)
        self._states.add(updated)
        self._save_states()
        self._emit_states_modified()
        return True

    def save_states(self) -> bool:
        """Save all states to persistent storage."""
        return self._save_states()

    def _save_states(self) -> bool:
        """Internal method to save states."""
        return self._state_repo.save_all(
            self._states._items,
            self._states._protected_keys
        )

    def _emit_states_modified(self) -> None:
        """Emit states modified event."""
        if self.on_states_modified:
            self.on_states_modified()

    # ═══════════════════════════════════════════════════════════
    # Initialization
    # ═══════════════════════════════════════════════════════════

    def initialize(self, default_gif_path: Optional[Path] = None) -> None:
        """
        Initialize state system with defaults and load user customizations.

        Args:
            default_gif_path: Path to default idle GIF
        """
        # Create default idle state
        default_gif_id = None
        if default_gif_path and default_gif_path.is_file():
            default_gif_id = self._gif_repo.store_gif(default_gif_path, "idle")

        idle_state = State(
            key="idle",
            label="Idle",
            name_tag="doro",
            gif_id=default_gif_id,
        )
        self._states.add(idle_state)
        self._states.protect("idle")

        # Load custom states from JSON
        custom_states = self._state_repo.load_all()
        for state in custom_states.values():
            self._states.add(state)

        # Load movement states
        move_states = self._move_repo.load_all()
        for move_state in move_states.values():
            self._move_states.add(move_state)

        # Load transition states
        if self._transition_repo:
            transitions = self._transition_repo.load_all()
            for transition in transitions.values():
                self._transitions.add(transition)

        # Set initial state
        self._states.set_current("idle")

        # Ensure walking state exists
        self._ensure_walking_state()

        # Write initial state list
        self.write_state_list()

    def _ensure_walking_state(self) -> None:
        """Ensure a default walking movement state exists."""
        walking_key = "walking"

        # Check if movement state exists
        if not self._move_states.get(walking_key):
            walk_move = MoveState(
                key=walking_key,
                state_key=walking_key,
                direction="any",
                default_distance=60.0,
                default_speed="med",
            )
            self._move_states.add(walk_move)

        # Ensure corresponding display state exists
        if not self._states.get(walking_key):
            # Try to find walking.gif using encapsulated method
            walk_gif_path = self._gif_repo.get_move_storage_path(walking_key)
            gif_id = None
            if walk_gif_path.is_file():
                gif_id = self._gif_repo.store_gif(walk_gif_path, walking_key)

            walk_state = State(
                key=walking_key,
                label="Walking",
                name_tag="doro",
                gif_id=gif_id,
            )
            self._states.add(walk_state)
            self._states.protect(walking_key)

    # ═══════════════════════════════════════════════════════════
    # State Operations
    # ═══════════════════════════════════════════════════════════

    def set_state(self, key: str, *, force: bool = False) -> bool:
        """
        Set current state.

        Args:
            key: State key to switch to
            force: If True, bypass transition protection (used by MovementManager)

        Returns:
            True if successful, False if state not found or rejected

        Protection:
            - Rejects requests during transitions (unless force=True)
            - Ensures state integrity during transition animations
        """
        # Check transition protection
        if self._is_transitioning and not force:
            logger.warning(f"State change rejected: '{key}' (transition in progress)")
            return False

        old_key = self._states._current_key
        if not self._states.set_current(key):
            logger.warning(f"Failed to set state: '{key}' not found")
            return False

        logger.info(f"State changed: {old_key} -> {key}" + (" [forced]" if force else ""))

        # Emit event
        state = self._states.get(key)
        if self.on_state_changed and state:
            event = StateChangeEvent(old_key, key, state)
            self.on_state_changed(event)

        return True

    # ═══════════════════════════════════════════════════════════
    # Transition Lock Management
    # ═══════════════════════════════════════════════════════════

    def begin_transition(self) -> bool:
        """
        Begin a transition animation, locking state changes.

        Prevents non-forced state changes during transition playback.
        Only forced state changes (force=True) can bypass this lock.

        Returns:
            True if lock acquired, False if already transitioning

        Usage:
            # Before playing transition GIF
            if service.begin_transition():
                play_transition_gif()
                # ... wait for completion ...
                service.end_transition()
        """
        if self._is_transitioning:
            logger.warning("Transition already in progress, cannot begin new transition")
            return False

        self._is_transitioning = True
        logger.debug("Transition lock acquired")
        return True

    def end_transition(self) -> bool:
        """
        End a transition animation, unlocking state changes.

        Allows normal state changes to proceed after transition playback.

        Returns:
            True if lock released, False if no transition was in progress

        Usage:
            # After transition GIF completes
            service.end_transition()
        """
        if not self._is_transitioning:
            logger.warning("No transition in progress, cannot end")
            return False

        self._is_transitioning = False
        logger.debug("Transition lock released")
        return True

    def is_transitioning(self) -> bool:
        """
        Check if a transition is currently in progress.

        Returns:
            True if transition lock is active, False otherwise
        """
        return self._is_transitioning

    def parse_state_from_action(self, action: str) -> Optional[str]:
        """
        Parse state key from action token in LLM responses.

        Handles various formats:
            (happy) -> "happy"
            (STATE:stand) -> "stand"
            (Mode: idle) -> "idle"
            (狀態:walking) -> "walking"

        Also handles:
            - Action aliases (e.g., "sleep" -> "idle")
            - Multiple normalized forms (spaces, underscores)
            - Label matching
            - Chinese prefixes (狀態, 模式)

        Args:
            action: Raw action token string from LLM response

        Returns:
            State key if valid non-movement state exists, None otherwise
        """
        from ...utils.actions import ACTION_ALIASES

        # Normalize action token
        raw = (action or "").strip()
        if not raw:
            return None

        lowered = raw.lower()

        # Remove common prefixes: "state", "mode", "status"
        for prefix in ("state", "mode", "status"):
            if lowered.startswith(prefix):
                raw = raw[len(prefix):]
                break
        else:
            # Handle Chinese prefixes
            if raw.startswith(("狀態", "模式")):
                raw = raw[2:]

        # Clean up separators
        raw = raw.lstrip(":：-_ ")
        normalized = raw.strip().lower()

        if not normalized:
            return None

        # Check aliases (e.g., "sleep" -> "idle")
        alias_target = ACTION_ALIASES.get(normalized)
        if alias_target and self.get_state(alias_target):
            if not self.is_movement_only_state(alias_target):
                return alias_target

        # Try various normalized forms
        candidates = {
            normalized,
            normalized.replace(" ", "_"),
            normalized.replace(" ", ""),
        }

        # Sanitize: keep only alphanumeric, -, _
        sanitized = "".join(ch for ch in normalized if ch.isalnum() or ch in ("-", "_"))
        if sanitized:
            candidates.add(sanitized)

        for candidate in candidates:
            if self.get_state(candidate):
                if not self.is_movement_only_state(candidate):
                    return candidate

        # Try matching by label
        result = self.find_state_by_label(normalized)
        if result and not self.is_movement_only_state(result):
            return result

        return None

    def add_state(self, key: str, label: str, copy_from: Optional[str] = None) -> Optional[State]:
        """
        Create a new custom state.

        Args:
            key: Unique state key
            label: Display label
            copy_from: Optional state key to copy settings from

        Returns:
            The created State or None if key already exists
        """
        if self._states.get(key):
            logger.warning(f"Cannot add state '{key}': already exists")
            return None

        # Check if movement-only
        if self._move_states.is_movement_only(key):
            logger.warning(f"Cannot add state '{key}': reserved for movement")
            return None

        # Create new state
        if copy_from:
            source = self._states.get(copy_from)
            if source:
                new_state = State(
                    key=key,
                    label=label,
                    name_tag=source.name_tag,
                    visual=source.visual,
                )
                logger.info(f"Added state '{key}' (copied from '{copy_from}')")
            else:
                new_state = State(key=key, label=label)
                logger.info(f"Added state '{key}' (copy source '{copy_from}' not found, using defaults)")
        else:
            new_state = State(key=key, label=label)
            logger.info(f"Added state '{key}'")

        self._states.add(new_state)
        self._state_repo.save_all(self._states._items, self._states._protected_keys)
        self.write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return new_state

    def remove_state(self, key: str) -> bool:
        """
        Remove a custom state.

        Returns:
            True if removed, False if protected or not found
        """
        # Get state before removing
        state = self._states.get(key)

        if not self._states.remove(key):
            logger.warning(f"Cannot remove state '{key}': protected or not found")
            return False

        logger.info(f"Removed state '{key}'")

        # Delete associated GIF
        if state and state.gif_id:
            self._gif_repo.delete(state.gif_id)
            logger.debug(f"Deleted GIF for removed state '{key}': {state.gif_id}")

        self._state_repo.save_all(self._states._items, self._states._protected_keys)
        self.write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return True

    def update_state_visual(self, key: str, **visual_changes: Any) -> Optional[State]:
        """
        Update visual config for a state.

        Returns:
            Updated state or None if not found
        """
        state = self._states.get(key)
        if not state:
            return None

        updated = state.with_visual(**visual_changes)
        self._states.add(updated)
        self._state_repo.save_all(self._states._items, self._states._protected_keys)

        # If this is current state, emit change event
        if self._states._current_key == key and self.on_state_changed:
            event = StateChangeEvent(key, key, updated)
            self.on_state_changed(event)

        return updated

    # ═══════════════════════════════════════════════════════════
    # GIF Management
    # ═══════════════════════════════════════════════════════════

    def set_gif(self, state_key: str, gif_path: Path) -> bool:
        """
        Set GIF for a state.

        Returns:
            True if successful
        """
        state = self._states.get(state_key)
        if not state:
            return False

        resource_id = self._gif_repo.store_gif(gif_path, state_key)
        if not resource_id:
            return False

        updated = state.with_changes(gif_id=resource_id)
        self._states.add(updated)

        # Save to persistent storage
        self._state_repo.save_all(self._states._items, self._states._protected_keys)

        # Emit change if current
        if self._states._current_key == state_key and self.on_state_changed:
            event = StateChangeEvent(state_key, state_key, updated)
            self.on_state_changed(event)

        return True

    # Legacy method name for compatibility
    def set_primary_gif(self, state_key: str, gif_path: Path) -> bool:
        """Legacy method. Use set_gif() instead."""
        return self.set_gif(state_key, gif_path)

    def get_gif_id(self, state_key: str) -> Optional[str]:
        """
        Get GIF resource ID for a state.

        Returns:
            Resource ID or None
        """
        state = self._states.get(state_key)
        return state.gif_id if state else None

    # ═══════════════════════════════════════════════════════════
    # Movement State Operations
    # ═══════════════════════════════════════════════════════════

    def add_move_state(
        self,
        key: str,
        state_key: str,
        direction: str = "any",
        distance: Optional[float] = None,
        speed: str = "med",
    ) -> MoveState:
        """Create or update a movement state."""
        move_state = MoveState(
            key=key,
            state_key=state_key,
            direction=direction,
            default_distance=distance,
            default_speed=speed,
        )
        self._move_states.add(move_state)
        self._move_repo.save_all(self._move_states._items)
        self.write_state_list()
        return move_state

    def remove_move_state(self, key: str) -> bool:
        """Remove a movement state."""
        if not self._move_states.remove(key):
            return False

        self._move_repo.save_all(self._move_states._items)
        self.write_state_list()
        return True

    def add_transition(
        self,
        transition: TransitionState,
    ) -> bool:
        """Create or update a transition state."""
        self._transitions.add(transition)
        if self._transition_repo:
            return self._transition_repo.save_all(self._transitions._items)
        return True

    def remove_transition(self, key: str) -> bool:
        """Remove a transition state."""
        if not self._transitions.remove(key):
            return False

        if self._transition_repo:
            return self._transition_repo.save_all(self._transitions._items)
        return True

    def find_move_state_by_direction(self, direction: str) -> Optional[str]:
        """
        Find a random movement state matching direction.

        Returns:
            State key to use for this movement
        """
        matches = self._move_states.find_by_direction(direction)
        if not matches:
            return None

        # Pick random match
        move_state = random.choice(matches)

        # Verify display state exists
        if self._states.get(move_state.state_key):
            return move_state.state_key

        return None

    # ═══════════════════════════════════════════════════════════
    # Persistence
    # ═══════════════════════════════════════════════════════════

    def write_state_list(self) -> str:
        """Write state summary for LLM context."""
        # Collect GIF path information (encapsulation: don't pass gif_repo)
        gif_paths: dict[str, Optional[Path]] = {}
        for key, state in self._states._items.items():
            if state.gif_id:
                gif_paths[key] = self._gif_repo.get_path(state.gif_id)
            else:
                gif_paths[key] = None

        return self._state_list_writer.write(
            self._states._items,
            self._move_states._items,
            gif_paths,
            self._move_states._movement_only_keys,
        )
