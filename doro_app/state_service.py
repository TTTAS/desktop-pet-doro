"""
State management service - orchestrates state operations without UI coupling.

This is the NEW StateManager. The old one is 1565 lines of chaos.
This one has clear responsibilities and no Window dependency.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Callable, Optional

from .state_models import MoveState, MoveStateCollection, State, StateChangeEvent, StateCollection, VisualConfig
from .state_repository import GifRepository, MoveStateRepository, StateListWriter, StateRepository


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
    ):
        # Private - encapsulated repositories
        self._state_repo = state_repo
        self._move_repo = move_repo
        self._gif_repo = gif_repo
        self._state_list_writer = StateListWriter(state_list_path)

        # Private - encapsulated collections
        self._states = StateCollection()
        self._move_states = MoveStateCollection()

        # Event callbacks (public - set by Window or controller)
        self.on_state_changed: Optional[Callable[[StateChangeEvent], None]] = None
        self.on_states_modified: Optional[Callable[[], None]] = None

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

    def find_state_by_label(self, label_query: str) -> Optional[str]:
        """Find a state key by searching labels (case-insensitive)."""
        query_lower = label_query.lower().strip()
        for key in self._states.all_keys():
            state = self._states.get(key)
            if state and state.label.lower() == query_lower:
                return key
        return None

    # ═══════════════════════════════════════════════════════════
    # Public API - State Modification
    # ═══════════════════════════════════════════════════════════

    def update_state(self, key: str, **changes) -> bool:
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

    def update_visual_config(self, key: str, **visual_changes) -> bool:
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
            default_gif_id = self._gif_repo.store_gif(default_gif_path, "idle", variant=False)

        idle_state = State(
            key="idle",
            label="Idle",
            name_tag="doro",
            primary_gif_id=default_gif_id,
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

        # Set initial state
        self._states.set_current("idle")

        # Ensure walking state exists
        self._ensure_walking_state()

        # Write initial state list
        self._write_state_list()

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
            # Try to find walking.gif
            walk_gif_path = self._gif_repo.storage_dir.parent / "ACTION" / "MOVE" / "walking.gif"
            gif_id = None
            if walk_gif_path.is_file():
                gif_id = self._gif_repo.store_gif(walk_gif_path, walking_key)

            walk_state = State(
                key=walking_key,
                label="Walking",
                name_tag="doro",
                primary_gif_id=gif_id,
            )
            self._states.add(walk_state)
            self._states.protect(walking_key)

    # ═══════════════════════════════════════════════════════════
    # State Operations
    # ═══════════════════════════════════════════════════════════

    def set_state(self, key: str) -> bool:
        """
        Set current state.

        Returns:
            True if successful, False if state not found
        """
        old_key = self._states._current_key
        if not self._states.set_current(key):
            return False

        # Load GIF variants if needed
        state = self._states.get(key)
        if state:
            self._refresh_gif_variants(key)

        # Emit event
        if self.on_state_changed and state:
            event = StateChangeEvent(old_key, key, state)
            self.on_state_changed(event)

        return True

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
            return None

        # Check if movement-only
        if self._move_states.is_movement_only(key):
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
            else:
                new_state = State(key=key, label=label)
        else:
            new_state = State(key=key, label=label)

        self._states.add(new_state)
        self._state_repo.save_all(self._states._states, self._states._protected_keys)
        self._write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return new_state

    def remove_state(self, key: str) -> bool:
        """
        Remove a custom state.

        Returns:
            True if removed, False if protected or not found
        """
        if not self._states.remove(key):
            return False

        # Delete associated GIF
        state = self._states.get(key)
        if state and state.primary_gif_id:
            self._gif_repo.delete(state.primary_gif_id)

        # Delete variants
        for variant_id in state.variant_gif_ids if state else []:
            self._gif_repo.delete(variant_id)

        self._state_repo.save_all(self._states._states, self._states._protected_keys)
        self._write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return True

    def update_state_visual(self, key: str, **visual_changes) -> Optional[State]:
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
        self._state_repo.save_all(self._states._states, self._states._protected_keys)

        # If this is current state, emit change event
        if self._states._current_key == key and self.on_state_changed:
            event = StateChangeEvent(key, key, updated)
            self.on_state_changed(event)

        return updated

    # ═══════════════════════════════════════════════════════════
    # GIF Management
    # ═══════════════════════════════════════════════════════════

    def set_primary_gif(self, state_key: str, gif_path: Path) -> bool:
        """
        Set primary GIF for a state.

        Returns:
            True if successful
        """
        state = self._states.get(state_key)
        if not state:
            return False

        resource_id = self._gif_repo.store_gif(gif_path, state_key, variant=False)
        if not resource_id:
            return False

        updated = state.with_changes(primary_gif_id=resource_id)
        self._states.add(updated)
        self._refresh_gif_variants(state_key)

        # Emit change if current
        if self._states._current_key == state_key and self.on_state_changed:
            event = StateChangeEvent(state_key, state_key, updated)
            self.on_state_changed(event)

        return True

    def add_gif_variant(self, state_key: str, gif_path: Path) -> bool:
        """
        Add a GIF variant for a state.

        Returns:
            True if successful
        """
        state = self._states.get(state_key)
        if not state:
            return False

        resource_id = self._gif_repo.store_gif(gif_path, state_key, variant=True)
        if not resource_id:
            return False

        self._refresh_gif_variants(state_key)
        return True

    def remove_gif_variant(self, state_key: str, resource_id: str) -> bool:
        """Remove a GIF variant."""
        if not self._gif_repo.delete(resource_id):
            return False

        self._refresh_gif_variants(state_key)
        return True

    def _refresh_gif_variants(self, state_key: str) -> None:
        """Refresh variant list for a state from filesystem."""
        state = self._states.get(state_key)
        if not state:
            return

        # Get all variants from repository
        variant_ids = self._gif_repo.list_variants(state_key)

        # Build complete variant list (primary + variants)
        all_variants = []
        if state.primary_gif_id:
            all_variants.append(state.primary_gif_id)
        all_variants.extend(variant_ids)

        # Update state
        updated = state.with_changes(variant_gif_ids=tuple(all_variants))
        self._states.add(updated)

    def pick_random_variant(self, state_key: str) -> Optional[str]:
        """
        Pick a random GIF variant for a state.

        Returns:
            Resource ID or None
        """
        state = self._states.get(state_key)
        if not state or not state.variant_gif_ids:
            return state.primary_gif_id if state else None

        return random.choice(state.variant_gif_ids)

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
        self._move_repo.save_all(self._move_states._move_states)
        self._write_state_list()
        return move_state

    def remove_move_state(self, key: str) -> bool:
        """Remove a movement state."""
        if not self._move_states.remove(key):
            return False

        self._move_repo.save_all(self._move_states._move_states)
        self._write_state_list()
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
    # Queries
    # ═══════════════════════════════════════════════════════════

    def visible_state_keys(self) -> list[str]:
        """Get keys for states visible in UI (not movement-only)."""
        return self._states.visible_keys(self._move_states._movement_only_keys)

    def find_state_by_label(self, label: str) -> Optional[str]:
        """Find state key by label (case-insensitive)."""
        label_lower = label.lower()
        for key in self._states.all_keys():
            state = self._states.get(key)
            if state and state.label.lower() == label_lower:
                return key
        return None

    # ═══════════════════════════════════════════════════════════
    # Persistence
    # ═══════════════════════════════════════════════════════════

    def _write_state_list(self) -> str:
        """Write state summary for LLM context."""
        return self._state_list_writer.write(
            self._states._states,
            self._move_states._move_states,
            self._gif_repo,
            self._move_states._movement_only_keys,
        )
