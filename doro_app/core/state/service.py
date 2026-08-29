"""
State management service - orchestrates state operations without UI coupling.

This is the NEW StateManager. The old one is 1565 lines of chaos.
This one has clear responsibilities and no Window dependency.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

from ...utils.logger import get_logger
from ..exceptions import ConfigSaveError, GifNotFoundError, GifStorageError
from .state_parser import StateParser
from .transition_coordinator import TransitionCoordinator
from .models import (
    MoveState,
    MoveStateCollection,
    State,
    StateChangeEvent,
    StateCollection,
    Transition,
    normalize_state_key,
)
from .repository import (
    GifRepository,
    MoveStateRepository,
    StateListWriter,
    StateRepository,
    TransitionRepository,
)

if TYPE_CHECKING:
    from ..movement.repository import MovementRepository

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
        transition_repo: Optional[TransitionRepository] = None,
        *,
        transition_gif_repo: GifRepository,
        movement_repo: Optional[MovementRepository] = None,
    ):
        self._state_repo = state_repo
        self._move_repo = move_repo
        self._gif_repo = gif_repo
        self._transition_gif_repo = transition_gif_repo
        self._transition_repo = transition_repo
        self._movement_repo = movement_repo
        self._state_list_writer = StateListWriter(state_list_path)

        self._transition_coordinator = TransitionCoordinator(transition_repo)
        self._state_parser = StateParser()

        self._states = StateCollection()
        self._move_states = MoveStateCollection()

        self.on_state_changed: Optional[Callable[[StateChangeEvent], None]] = None
        self.on_states_modified: Optional[Callable[[], None]] = None

    def _store_gif(self, source_path: Path, context_key: str) -> Optional[str]:
        try:
            return self._gif_repo.store_gif(source_path, context_key)
        except (GifNotFoundError, GifStorageError) as e:
            logger.error(f"Failed to store GIF for '{context_key}': {e}")
            return None

    def _add_gif(self, repo: GifRepository, source_path: Path, key: str) -> Optional[str]:
        try:
            return repo.add_gif(source_path, key)
        except (GifNotFoundError, GifStorageError) as e:
            logger.error(f"Failed to add GIF for '{key}': {e}")
            return None

    def get_gif_path(self, state_key: str) -> Optional[Path]:
        random_path = self._gif_repo.pick_random_gif(state_key)
        if random_path:
            return random_path

        state = self._states.get(state_key)
        if state and state.gif_id:
            path = self._gif_repo.get_path(state.gif_id)
            if path:
                return path

        if self._move_states.is_movement_only(state_key):
            if self._movement_repo:
                anim_path = self._movement_repo.resolve_animation_path(state_key)
                if anim_path:
                    return anim_path
            move_path = self._gif_repo.get_move_storage_path(state_key)
            if move_path.is_file():
                return move_path

        return None

    def get_gif_path_by_id(self, gif_id: str) -> Optional[Path]:
        return self._gif_repo.get_path(gif_id)

    def store_gif(self, source_path: Path, state_key: str) -> Optional[str]:
        return self._store_gif(source_path, state_key)

    def delete_gif(self, gif_id: str) -> bool:
        return self._gif_repo.delete(gif_id)

    def get_state_storage_path(self, state_key: str) -> Path:
        return self._gif_repo.get_state_storage_path(state_key)

    def get_move_storage_path(self, move_key: str) -> Path:
        return self._gif_repo.get_move_storage_path(move_key)

    def sanitize_state_key(self, key: str) -> str:
        return self._gif_repo.sanitize_filename(key)

    def get_state(self, key: str) -> Optional[State]:
        return self._states.get(key)

    def has_state(self, key: str) -> bool:
        return self._states.get(key) is not None

    def get_current_state(self) -> Optional[State]:
        return self._states.current()

    def get_current_state_key(self) -> Optional[str]:
        return self._states.current_key()

    def visible_state_keys(self) -> list[str]:
        return self._states.visible_keys(set(self._move_states.movement_only_keys()))

    def all_state_keys(self) -> list[str]:
        return self._states.all_keys()

    def is_state_protected(self, key: str) -> bool:
        return self._states.is_protected(key)

    def is_movement_only_state(self, key: str) -> bool:
        return self._move_states.is_movement_only(key)

    def get_move_state(self, key: str) -> Optional[MoveState]:
        return self._move_states.get(key)

    def all_move_state_keys(self) -> list[str]:
        return self._move_states.all_keys()

    def find_move_states_by_direction(self, direction_slug: str) -> list[MoveState]:
        return self._move_states.find_by_direction(direction_slug)

    def get_default_movement_state(self) -> Optional[str]:
        if self.get_state("walking"):
            return "walking"
        for move_state in self._move_states.find_by_direction("any"):
            if self.get_state(move_state.state_key):
                return move_state.state_key
        return None

    def find_state_by_label(self, label_query: str) -> Optional[str]:
        query_lower = label_query.lower().strip()
        for key in self._states.all_keys():
            state = self._states.get(key)
            if state and state.label.lower() == query_lower:
                return key
        return None

    def get_transition(self, key: str) -> Optional[Transition]:
        return self._transition_coordinator.get(key)

    def all_transition_keys(self) -> list[str]:
        return self._transition_coordinator.all_keys()

    def find_transition(self, from_state: str, to_state: str) -> Optional[Transition]:
        return self._transition_coordinator.find(from_state, to_state)

    def get_transition_gif_path(self, transition_key: str) -> Optional[Path]:
        return self._transition_gif_repo.pick_random_gif(transition_key)

    def list_transition_gif_paths(self, transition_key: str) -> list[Path]:
        return self._transition_gif_repo.list_gifs(transition_key)

    def add_transition_gif(self, transition_key: str, gif_path: Path) -> bool:
        resource_id = self._add_gif(self._transition_gif_repo, gif_path, transition_key)
        return resource_id is not None

    def remove_transition_gif(self, transition_key: str, filename: str) -> bool:
        return self._transition_gif_repo.remove_gif(transition_key, filename)

    def ensure_action_state(
        self,
        key: str,
        label: str,
        gif_id: Optional[str] = None,
    ) -> None:
        existing = self._states.get(key)
        if existing is None:
            new_state = State(key=key, label=label, name_tag="doro", gif_id=gif_id)
            self._states.add(new_state)
        elif gif_id is not None and existing.gif_id != gif_id:
            self._states.add(existing.with_changes(gif_id=gif_id))

        self._states.protect(key)
        self._states.hide(key)

    def update_state(self, key: str, **changes: Any) -> bool:
        state = self._states.get(key)
        if not state:
            return False

        updated = state.with_changes(**changes)
        self._states.add(updated)
        self._save_states()
        self._emit_states_modified()
        return True

    def update_visual_config(self, key: str, **visual_changes: Any) -> bool:
        state = self._states.get(key)
        if not state:
            return False

        updated = state.with_visual(**visual_changes)
        self._states.add(updated)
        self._save_states()
        self._emit_states_modified()
        return True

    def save_states(self) -> bool:
        return self._save_states()

    def _save_states(self) -> bool:
        try:
            self._state_repo.save_all(
                self._states.items(),
                set(self._states.protected_keys()),
            )
            return True
        except ConfigSaveError as e:
            logger.error(f"Failed to save states: {e}")
            return False

    def _emit_states_modified(self) -> None:
        if self.on_states_modified:
            self.on_states_modified()

    def initialize(self, default_gif_path: Optional[Path] = None) -> None:
        default_gif_id = None
        if default_gif_path and default_gif_path.is_file():
            default_gif_id = self._store_gif(default_gif_path, "idle")

        idle_state = State(
            key="idle",
            label="Idle",
            name_tag="doro",
            gif_id=default_gif_id,
        )
        self._states.add(idle_state)
        self._states.protect("idle")

        custom_states = self._state_repo.load_all()
        for state in custom_states.values():
            self._states.add(state)

        move_states = self._move_repo.load_all()
        for move_state in move_states.values():
            self._move_states.add(move_state)

        self._transition_coordinator.load_from_repo()
        self._states.set_current("idle")
        self._ensure_movement_states()
        self.write_state_list()

    def _ensure_movement_states(self) -> None:
        if self._movement_repo:
            for key, entry in self._movement_repo.entries.items():
                if not self._move_states.get(key):
                    move = MoveState(
                        key=entry.key,
                        state_key=entry.state_key,
                        direction=entry.direction,
                        default_distance=entry.default_distance,
                        default_speed=entry.default_speed,
                    )
                    self._move_states.add(move)

                if not self._states.get(entry.state_key):
                    display_state = State(
                        key=entry.state_key,
                        label=entry.state_key.capitalize(),
                        name_tag="doro",
                    )
                    self._states.add(display_state)
                    self._states.protect(entry.state_key)
        else:
            walking_key = "walking"
            if not self._move_states.get(walking_key):
                walk_move = MoveState(
                    key=walking_key,
                    state_key=walking_key,
                    direction="any",
                    default_distance=60.0,
                    default_speed="med",
                )
                self._move_states.add(walk_move)

            if not self._states.get(walking_key):
                walk_state = State(
                    key=walking_key,
                    label="Walking",
                    name_tag="doro",
                )
                self._states.add(walk_state)
                self._states.protect(walking_key)

    def set_state(self, key: str, *, force: bool = False) -> bool:
        key = normalize_state_key(key)
        if self._transition_coordinator.is_active() and not force:
            logger.warning(f"State change rejected: '{key}' (transition in progress)")
            return False

        old_key = self._states.current_key()
        if not self._states.set_current(key):
            logger.warning(f"Failed to set state: '{key}' not found")
            return False

        logger.info(f"State changed: {old_key} -> {key}" + (" [forced]" if force else ""))

        state = self._states.get(key)
        if self.on_state_changed and state:
            event = StateChangeEvent(old_key, key, state)
            self.on_state_changed(event)

        return True

    def begin_transition(self) -> bool:
        return self._transition_coordinator.begin()

    def end_transition(self) -> bool:
        return self._transition_coordinator.end()

    def is_transitioning(self) -> bool:
        return self._transition_coordinator.is_active()

    def parse_state_from_action(self, action: str) -> Optional[str]:
        return self._state_parser.parse(action, self)

    def add_state(self, key: str, label: str, copy_from: Optional[str] = None) -> Optional[State]:
        if self._states.get(key):
            logger.warning(f"Cannot add state '{key}': already exists")
            return None

        if self._move_states.is_movement_only(key):
            logger.warning(f"Cannot add state '{key}': reserved for movement")
            return None

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
                logger.info(
                    f"Added state '{key}' (copy source '{copy_from}' not found, using defaults)"
                )
        else:
            new_state = State(key=key, label=label)
            logger.info(f"Added state '{key}'")

        self._states.add(new_state)
        self._state_repo.save_all(
            self._states.items(),
            set(self._states.protected_keys()),
        )
        self.write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return self._states.get(key)

    def remove_state(self, key: str) -> bool:
        if not self._states.remove(key):
            logger.warning(f"Cannot remove state '{key}': protected or not found")
            return False

        logger.info(f"Removed state '{key}'")

        self._gif_repo.delete_all_gifs(key)
        logger.debug(f"Deleted GIFs for removed state '{key}'")

        self._state_repo.save_all(
            self._states.items(),
            set(self._states.protected_keys()),
        )
        self.write_state_list()

        if self.on_states_modified:
            self.on_states_modified()

        return True

    def update_state_visual(self, key: str, **visual_changes: Any) -> Optional[State]:
        state = self._states.get(key)
        if not state:
            return None

        updated = state.with_visual(**visual_changes)
        self._states.add(updated)
        self._state_repo.save_all(
            self._states.items(),
            set(self._states.protected_keys()),
        )

        if self._states.current_key() == normalize_state_key(key) and self.on_state_changed:
            event = StateChangeEvent(key, updated.key, updated)
            self.on_state_changed(event)

        return updated

    def set_gif(self, state_key: str, gif_path: Path) -> bool:
        state = self._states.get(state_key)
        if not state:
            return False

        resource_id = self._store_gif(gif_path, state_key)
        if not resource_id:
            return False

        updated = state.with_changes(gif_id=resource_id)
        self._states.add(updated)

        self._state_repo.save_all(
            self._states.items(),
            set(self._states.protected_keys()),
        )

        if self._states.current_key() == normalize_state_key(state_key) and self.on_state_changed:
            event = StateChangeEvent(state_key, updated.key, updated)
            self.on_state_changed(event)

        return True

    def get_gif_id(self, state_key: str) -> Optional[str]:
        state = self._states.get(state_key)
        return state.gif_id if state else None

    def add_gif(self, state_key: str, gif_path: Path) -> bool:
        state = self._states.get(state_key)
        if not state:
            return False

        resource_id = self._add_gif(self._gif_repo, gif_path, state_key)
        if not resource_id:
            return False

        updated = state.with_changes(gif_id=resource_id)
        self._states.add(updated)
        self._state_repo.save_all(
            self._states.items(),
            set(self._states.protected_keys()),
        )

        return True

    def list_gif_paths(self, state_key: str) -> list[Path]:
        return self._gif_repo.list_gifs(state_key)

    def remove_gif(self, state_key: str, filename: str) -> bool:
        return self._gif_repo.remove_gif(state_key, filename)

    def delete_all_gifs(self, state_key: str) -> bool:
        return self._gif_repo.delete_all_gifs(state_key)

    def add_move_state(
        self,
        key: str,
        state_key: str,
        direction: str = "any",
        distance: Optional[float] = None,
        speed: str = "med",
    ) -> MoveState:
        move_state = MoveState(
            key=key,
            state_key=state_key,
            direction=direction,
            default_distance=distance,
            default_speed=speed,
        )
        self._move_states.add(move_state)
        try:
            self._move_repo.save_all(self._move_states.items())
        except ConfigSaveError as e:
            logger.error(f"Failed to save move states: {e}")
        self.write_state_list()
        stored = self._move_states.get(key)
        return stored if stored is not None else move_state

    def remove_move_state(self, key: str) -> bool:
        if not self._move_states.remove(key):
            return False

        try:
            self._move_repo.save_all(self._move_states.items())
        except ConfigSaveError as e:
            logger.error(f"Failed to save move states: {e}")
        self.write_state_list()
        return True

    def add_transition(
        self,
        transition: Transition,
    ) -> bool:
        self._transition_coordinator.add(transition)
        if self._transition_repo:
            try:
                self._transition_repo.save_all(self._transition_coordinator.get_all_items())
            except ConfigSaveError as e:
                logger.error(f"Failed to save transitions: {e}")
                return False
        return True

    def remove_transition(self, key: str) -> bool:
        if not self._transition_coordinator.remove(key):
            return False

        if self._transition_repo:
            try:
                self._transition_repo.save_all(self._transition_coordinator.get_all_items())
            except ConfigSaveError as e:
                logger.error(f"Failed to save transitions: {e}")
                return False

        try:
            self._transition_gif_repo.delete_all_gifs(key)
        except Exception as e:
            logger.warning(f"Failed to clean up GIF files for transition '{key}': {e}")

        return True

    def find_move_state_by_direction(self, direction: str) -> Optional[str]:
        matches = self._move_states.find_by_direction(direction)
        if not matches:
            return None

        move_state = random.choice(matches)

        if self._states.get(move_state.state_key):
            return move_state.state_key

        return None

    def write_state_list(self) -> str:
        gif_paths: dict[str, Optional[Path]] = {}
        gif_counts: dict[str, int] = {}
        for key, state in self._states.items().items():
            multi_gifs = self._gif_repo.list_gifs(key)
            if multi_gifs:
                gif_paths[key] = multi_gifs[0]
                gif_counts[key] = len(multi_gifs)
            elif state.gif_id:
                gif_paths[key] = self._gif_repo.get_path(state.gif_id)
                gif_counts[key] = 1 if gif_paths[key] else 0
            else:
                if self._move_states.is_movement_only(key):
                    anim_path = None
                    if self._movement_repo:
                        anim_path = self._movement_repo.resolve_animation_path(key)
                    if not anim_path:
                        move_path = self._gif_repo.get_move_storage_path(key)
                        if move_path.is_file():
                            anim_path = move_path
                    if anim_path:
                        gif_paths[key] = anim_path
                        gif_counts[key] = 1
                        continue
                gif_paths[key] = None
                gif_counts[key] = 0

        return self._state_list_writer.write(
            self._states.items(),
            self._move_states.items(),
            gif_paths,
            set(self._move_states.movement_only_keys()),
            gif_counts=gif_counts,
        )
