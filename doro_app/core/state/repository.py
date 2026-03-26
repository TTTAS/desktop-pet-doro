"""State persistence layer - handles all file I/O for states and GIFs."""

from __future__ import annotations

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...utils.logger import get_logger
from ..exceptions import (
    ConfigLoadError,
    ConfigSaveError,
    GifNotFoundError,
    GifStorageError,
)
from .models import MoveState, State, Transition, VisualConfig

logger = get_logger(__name__)

# Supported animated image formats (GIF, APNG, WebP)
ANIMATED_EXTENSIONS = frozenset({".gif", ".apng", ".webp"})


def _is_animated_file(path: Path) -> bool:
    """Check if a path has a supported animated image extension."""
    return path.suffix.lower() in ANIMATED_EXTENSIONS and path.is_file()


class GifRepository:
    """
    Manages GIF file storage and retrieval.

    Responsibilities:
    - Store GIFs in organized directory structure
    - Generate unique resource IDs
    - Handle file operations (copy, delete)
    - NO business logic
    - NO UI
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def store_gif(self, source_path: Path, state_key: str) -> str:
        """
        Copy a GIF into storage.

        Args:
            source_path: Source GIF file
            state_key: State this GIF belongs to

        Returns:
            Resource ID (relative path)

        Raises:
            GifNotFoundError: Source file does not exist
            GifStorageError: Failed to copy file
        """
        if not source_path.is_file():
            raise GifNotFoundError(str(source_path))

        dest_path = self._primary_path(state_key)

        # If source and dest are the same file, just return resource ID
        try:
            if source_path.resolve() == dest_path.resolve():
                return self._to_resource_id(dest_path)
        except OSError as e:
            raise GifStorageError(f"Failed to resolve path: {e}")

        try:
            shutil.copy2(source_path, dest_path)
            return self._to_resource_id(dest_path)
        except OSError as e:
            raise GifStorageError(f"Failed to copy GIF: {e}")

    def get_path(self, resource_id: str) -> Optional[Path]:
        """
        Resolve resource ID to actual file path.

        Returns:
            Absolute path if file exists and is within storage_dir, None otherwise
        """
        # Security: Prevent path traversal attacks
        try:
            # Resolve the full path
            path = (self.storage_dir / resource_id).resolve()
            storage_resolved = self.storage_dir.resolve()

            # Ensure the resolved path is within storage_dir
            # This prevents attacks like "../../etc/passwd"
            path.relative_to(storage_resolved)

            # Check if file exists
            if path.is_file():
                logger.debug(f"GIF path resolved: {resource_id} -> {path}")
                return path
            else:
                logger.warning(f"GIF file not found: {resource_id}")
                return None

        except ValueError as e:
            # Path is outside storage_dir
            logger.error(f"Path traversal attempt blocked: {resource_id} (error: {e})")
            return None
        except OSError as e:
            # File system error
            logger.error(f"Failed to resolve GIF path {resource_id}: {e}")
            return None

    def delete(self, resource_id: str) -> bool:
        """
        Delete a GIF by resource ID.

        Returns:
            False if file doesn't exist, True if deleted successfully

        Raises:
            GifStorageError: Failed to delete file
        """
        path = self.get_path(resource_id)
        if not path:
            return False

        try:
            path.unlink()
            return True
        except OSError as e:
            raise GifStorageError(f"Failed to delete GIF: {e}")

    # ═══════════════════════════════════════════════════════════
    # Public API - Path Utilities
    # ═══════════════════════════════════════════════════════════

    def get_state_storage_path(self, state_key: str) -> Path:
        """
        Get the storage path for a state's GIF.

        Args:
            state_key: State identifier

        Returns:
            Path where the GIF should be stored
        """
        return self._primary_path(state_key)

    def get_move_storage_path(self, move_key: str) -> Path:
        """
        Get the storage path for a movement action's GIF.

        Args:
            move_key: Movement action key (e.g., "walking", "running")

        Returns:
            Path where the move GIF should be stored
        """
        safe_key = self._sanitize_key(move_key)
        move_dir = self.storage_dir.parent / "ACTION" / "MOVE"
        for ext in ANIMATED_EXTENSIONS:
            p = move_dir / f"{safe_key}{ext}"
            if p.is_file():
                return p
        return move_dir / f"{safe_key}.gif"

    def sanitize_filename(self, key: str) -> str:
        """
        Sanitize a key for safe use in filenames.

        Args:
            key: Raw key string

        Returns:
            Sanitized filename-safe string
        """
        return self._sanitize_key(key)

    # ═══════════════════════════════════════════════════════════
    # Multi-GIF Operations
    # ═══════════════════════════════════════════════════════════

    def list_gifs(self, state_key: str) -> list[Path]:
        """
        List all GIF files in a state's subfolder.

        Returns:
            Sorted list of .gif paths (empty if no subfolder or no gifs)
        """
        state_dir = self._state_dir(state_key)
        if not state_dir.is_dir():
            return []
        return sorted(p for p in state_dir.iterdir() if _is_animated_file(p))

    def pick_random_gif(self, state_key: str) -> Optional[Path]:
        """
        Pick a random GIF for a state.

        Priority:
        1. Random pick from subfolder {storage_dir}/{key}/ if it has .gif files
        2. Fall back to single file {storage_dir}/{key}.gif

        Returns:
            Path to a GIF file, or None if no GIF exists
        """
        gifs = self.list_gifs(state_key)
        if gifs:
            return random.choice(gifs)

        # Fallback: single file
        primary = self._primary_path(state_key)
        return primary if primary.is_file() else None

    def add_gif(self, source_path: Path, state_key: str) -> str:
        """
        Add a GIF to a state's subfolder.

        Creates the subfolder if needed. If a single-file GIF ({key}.gif) exists,
        it is automatically migrated into the subfolder first.
        Auto-generates sequential filenames ({key}_1.gif, {key}_2.gif, ...).

        Args:
            source_path: Source GIF file
            state_key: State this GIF belongs to

        Returns:
            Resource ID (e.g. 'stand/stand_2.gif')

        Raises:
            GifNotFoundError: Source file does not exist
            GifStorageError: Failed to copy file
        """
        if not source_path.is_file():
            raise GifNotFoundError(str(source_path))

        state_dir = self._state_dir(state_key)
        state_dir.mkdir(parents=True, exist_ok=True)

        safe_key = self._sanitize_key(state_key)

        # Preserve the source file extension (.gif, .apng, .webp, etc.)
        ext = source_path.suffix.lower() if source_path.suffix else ".gif"

        # Auto-migrate: move single file into subfolder if transitioning to multi
        primary = self._primary_path(state_key)
        if primary.is_file() and not self.list_gifs(state_key):
            migrated = state_dir / f"{safe_key}_1{primary.suffix}"
            try:
                shutil.move(str(primary), str(migrated))
            except OSError as e:
                raise GifStorageError(f"Failed to migrate single-file GIF: {e}")

        # Find next available index
        existing = self.list_gifs(state_key)
        index = len(existing) + 1
        dest = state_dir / f"{safe_key}_{index}{ext}"
        # Handle collision (shouldn't happen normally)
        while dest.exists():
            index += 1
            dest = state_dir / f"{safe_key}_{index}{ext}"

        try:
            shutil.copy2(source_path, dest)
            return self._to_resource_id(dest)
        except OSError as e:
            raise GifStorageError(f"Failed to copy GIF: {e}")

    def remove_gif(self, state_key: str, filename: str) -> bool:
        """
        Remove a specific GIF from a state's subfolder.

        Cleans up the subfolder if it becomes empty.

        Args:
            state_key: State key
            filename: Filename within the subfolder (e.g. 'stand_2.gif')

        Returns:
            True if deleted, False if not found
        """
        state_dir = self._state_dir(state_key)
        target = state_dir / filename
        if not target.is_file():
            return False

        # Security: ensure target is within state_dir
        try:
            target.resolve().relative_to(state_dir.resolve())
        except ValueError:
            logger.error(f"Path traversal attempt blocked: {filename}")
            return False

        try:
            target.unlink()
        except OSError as e:
            raise GifStorageError(f"Failed to delete GIF: {e}")

        # Clean up empty subfolder
        remaining = self.list_gifs(state_key)
        if not remaining and state_dir.is_dir():
            try:
                state_dir.rmdir()
            except OSError:
                pass  # Not empty (other non-gif files), leave it

        return True

    def delete_all_gifs(self, state_key: str) -> bool:
        """
        Delete all GIFs for a state (both single file and subfolder).

        Used when removing a state entirely.

        Returns:
            True if any files were deleted
        """
        deleted = False

        # Delete single file
        primary = self._primary_path(state_key)
        if primary.is_file():
            try:
                primary.unlink()
                deleted = True
            except OSError as e:
                raise GifStorageError(f"Failed to delete primary GIF: {e}")

        # Delete subfolder contents
        state_dir = self._state_dir(state_key)
        if state_dir.is_dir():
            for gif_file in state_dir.iterdir():
                if gif_file.is_file():
                    try:
                        gif_file.unlink()
                        deleted = True
                    except OSError as e:
                        raise GifStorageError(f"Failed to delete GIF {gif_file.name}: {e}")
            try:
                state_dir.rmdir()
            except OSError:
                pass  # Not empty, leave it

        return deleted

    # ═══════════════════════════════════════════════════════════
    # Private Implementation
    # ═══════════════════════════════════════════════════════════

    def _state_dir(self, state_key: str) -> Path:
        """Get subfolder path for a state's GIFs."""
        safe_key = self._sanitize_key(state_key)
        return self.storage_dir / safe_key

    def _primary_path(self, state_key: str) -> Path:
        """Get single-file sprite path for a state.

        Checks all supported animated formats (.gif, .apng, .webp)
        and returns the first match. Falls back to {key}.gif for
        backwards compatibility (e.g. when the file doesn't exist yet).
        """
        safe_key = self._sanitize_key(state_key)
        for ext in ANIMATED_EXTENSIONS:
            p = self.storage_dir / f"{safe_key}{ext}"
            if p.is_file():
                return p
        # Fallback: default to .gif for new files / non-existent paths
        return self.storage_dir / f"{safe_key}.gif"

    def _to_resource_id(self, path: Path) -> str:
        """Convert absolute path to resource ID."""
        try:
            return str(path.relative_to(self.storage_dir))
        except ValueError:
            return path.name

    def _sanitize_key(self, key: str) -> str:
        """Sanitize state key for use in filenames."""
        return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key) or "state"


class StateRepository:
    """
    Manages state persistence (JSON config files).

    Responsibilities:
    - Load/save state definitions from JSON
    - Convert between State objects and JSON
    - NO GIF management (use GifRepository)
    """

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_all(self) -> dict[str, State]:
        """
        Load all custom states from JSON.

        Returns:
            Dict of state_key -> State (empty dict if no config file exists)

        Raises:
            ConfigLoadError: Failed to read or parse config file
        """
        if not self.config_path.is_file():
            logger.debug(f"No state config file found at {self.config_path}")
            return {}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            logger.info(f"Loaded state config from {self.config_path}")
        except OSError as e:
            logger.error(f"Failed to read state config {self.config_path}: {e}")
            raise ConfigLoadError(str(self.config_path), str(e))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in state config {self.config_path}: {e}")
            raise ConfigLoadError(str(self.config_path), f"Invalid JSON: {e}")

        if not isinstance(data, dict):
            logger.error(f"State config is not a dict: {type(data)}")
            return {}

        states = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                logger.warning(f"Skipping invalid state entry '{key}': not a dict")
                continue
            try:
                state = self._from_dict(key, value)
                states[key] = state
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse state '{key}': {e}")
                continue

        logger.info(f"Loaded {len(states)} custom states")
        return states

    def save_all(self, states: dict[str, State], protected_keys: set[str]) -> None:
        """
        Save custom states to JSON.

        Args:
            states: All states
            protected_keys: Keys to exclude from save (built-in states)

        Raises:
            ConfigSaveError: Failed to save config file
        """
        # Only save custom states
        custom_states = {
            key: self._to_dict(state) for key, state in states.items() if key not in protected_keys
        }

        try:
            if custom_states:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps(custom_states, indent=2, ensure_ascii=False)
                self.config_path.write_text(content, encoding="utf-8")
                logger.info(f"Saved {len(custom_states)} custom states to {self.config_path}")
            else:
                # No custom states, remove file
                if self.config_path.exists():
                    self.config_path.unlink()
                    logger.info(f"Removed empty state config {self.config_path}")
        except OSError as e:
            logger.error(f"Failed to save states to {self.config_path}: {e}")
            raise ConfigSaveError(str(self.config_path), str(e))

    def _to_dict(self, state: State) -> dict[str, Any]:
        """Convert State to JSON-serializable dict."""
        data = {
            "label": state.label,
            "name_tag": state.name_tag,
            "bob_amplitude": state.visual.bob_amplitude,
            "scale_amplitude": state.visual.scale_amplitude,
            "gradient_top": state.visual.gradient_top,
            "gradient_mid": state.visual.gradient_mid,
            "gradient_bottom": state.visual.gradient_bottom,
            "cheeks_alpha": state.visual.cheeks_alpha,
            "blush_color": state.visual.blush_color,
            "eye_color": state.visual.eye_color,
            "bubble_visible": state.visual.bubble_visible,
            "bubble_alpha": state.visual.bubble_alpha,
        }

        # Save GIF reference
        if state.gif_id:
            data["gif_id"] = state.gif_id

        # Save Live2D model path
        if state.live2d_model_path:
            data["live2d_model_path"] = state.live2d_model_path

        return data

    def _from_dict(self, key: str, data: dict[str, Any]) -> State:
        """Convert JSON dict to State object."""
        label = data.get("label", key.capitalize())
        name_tag = data.get("name_tag", "doro")

        # Build VisualConfig from data
        visual_fields = {
            "bob_amplitude",
            "scale_amplitude",
            "gradient_top",
            "gradient_mid",
            "gradient_bottom",
            "cheeks_alpha",
            "blush_color",
            "eye_color",
            "bubble_visible",
            "bubble_alpha",
        }
        visual_data = {k: v for k, v in data.items() if k in visual_fields}
        visual = VisualConfig(**visual_data)

        # Load GIF reference (support both old and new format)
        gif_id = data.get("gif_id") or data.get("primary_gif_id")

        # Load Live2D model path
        live2d_model_path = data.get("live2d_model_path")

        return State(
            key=key,
            label=label,
            name_tag=name_tag,
            visual=visual,
            gif_id=gif_id,
            live2d_model_path=live2d_model_path,
        )


class MoveStateRepository:
    """Manages movement state persistence."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_all(self) -> dict[str, MoveState]:
        """
        Load movement states from JSON.

        Returns:
            Dict of move_key -> MoveState (empty dict if no config file exists)

        Raises:
            ConfigLoadError: Failed to read or parse config file
        """
        if not self.config_path.is_file():
            return {}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError as e:
            raise ConfigLoadError(str(self.config_path), str(e))
        except json.JSONDecodeError as e:
            raise ConfigLoadError(str(self.config_path), f"Invalid JSON: {e}")

        if not isinstance(data, dict):
            return {}

        move_states = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                move_state = MoveState(
                    key=key,
                    state_key=value["state_key"],
                    direction=value.get("direction", "any"),
                    default_distance=value.get("default_distance"),
                    default_speed=value.get("default_speed", "med"),
                )
                move_states[key] = move_state
            except (KeyError, ValueError, TypeError):
                continue

        return move_states

    def save_all(self, move_states: dict[str, MoveState]) -> None:
        """
        Save movement states to JSON.

        Raises:
            ConfigSaveError: Failed to save config file
        """
        data = {
            key: {
                "state_key": ms.state_key,
                "direction": ms.direction,
                "default_distance": ms.default_distance,
                "default_speed": ms.default_speed,
            }
            for key, ms in move_states.items()
        }

        try:
            if data:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps(data, indent=2, ensure_ascii=False)
                self.config_path.write_text(content, encoding="utf-8")
            else:
                if self.config_path.exists():
                    self.config_path.unlink()
        except OSError as e:
            raise ConfigSaveError(str(self.config_path), str(e))


class TransitionRepository:
    """Manages transition persistence."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_all(self) -> dict[str, Transition]:
        """
        Load transitions from JSON.

        Returns:
            Dict of transition_key -> Transition (empty dict if no config file exists)

        Raises:
            ConfigLoadError: Failed to read or parse config file
        """
        if not self.config_path.is_file():
            return {}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError as e:
            raise ConfigLoadError(str(self.config_path), str(e))
        except json.JSONDecodeError as e:
            raise ConfigLoadError(str(self.config_path), f"Invalid JSON: {e}")

        if not isinstance(data, dict):
            return {}

        transitions = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                transition = Transition(
                    key=key,
                    from_state=value["from_state"],
                    to_state=value["to_state"],
                    transition_gif_id=value.get("transition_gif_id"),
                )
                transitions[key] = transition
            except (KeyError, ValueError, TypeError):
                continue

        return transitions

    def save_all(self, transitions: dict[str, Transition]) -> None:
        """
        Save transitions to JSON.

        Raises:
            ConfigSaveError: Failed to save config file
        """
        data = {
            key: {
                "from_state": ts.from_state,
                "to_state": ts.to_state,
                "transition_gif_id": ts.transition_gif_id,
            }
            for key, ts in transitions.items()
        }

        try:
            if data:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps(data, indent=2, ensure_ascii=False)
                self.config_path.write_text(content, encoding="utf-8")
            else:
                if self.config_path.exists():
                    self.config_path.unlink()
        except OSError as e:
            raise ConfigSaveError(str(self.config_path), str(e))


class StateListWriter:
    """
    Writes human-readable state summaries for LLM context.

    This is a specialized writer, not part of core persistence.
    """

    def __init__(self, output_path: Path):
        self.output_path = output_path

    def write(
        self,
        states: dict[str, State],
        move_states: dict[str, MoveState],
        gif_paths: dict[str, Optional[Path]],
        movement_only_keys: set[str],
        gif_counts: Optional[dict[str, int]] = None,
    ) -> str:
        """
        Generate and write state list summary.

        Args:
            states: State definitions
            move_states: Movement state definitions
            gif_paths: Pre-resolved GIF paths for each state key
            movement_only_keys: Keys that are movement-only

        Returns:
            The generated text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的狀態為:"]

        # Regular states
        visible_keys = sorted(k for k in states.keys() if k not in movement_only_keys)
        for key in visible_keys:
            state: State = states[key]
            gif_info = self._gif_summary(key, gif_paths, gif_counts)
            action_type = self._action_type(key, move_states)
            lines.append(f"- ({key}) {state.label} | {action_type} | GIF: {gif_info}")

        # Movement-only states
        movement_keys = sorted(movement_only_keys)
        if movement_keys:
            lines.append("")
            lines.append("移動專用狀態:")
            for key in movement_keys:
                move_state: Optional[State] = states.get(key)
                if not move_state:
                    continue
                gif_info = self._gif_summary(key, gif_paths, gif_counts)
                direction = self._direction_for_state(key, move_states)
                lines.append(
                    f"- ({key}) {move_state.label} | type: movement ({direction}) | GIF: {gif_info}"
                )

        output = "\n".join(lines) + "\n"

        try:
            self.output_path.write_text(output, encoding="utf-8")
        except OSError:
            pass

        return output.strip()

    def _gif_summary(self, state_key: str, gif_paths: dict[str, Optional[Path]], gif_counts: Optional[dict[str, int]] = None) -> str:
        """Generate GIF summary string."""
        count = (gif_counts or {}).get(state_key, 0)
        if count > 1:
            return f"{count} GIFs"
        gif_path = gif_paths.get(state_key)
        return str(gif_path) if gif_path else "(no GIF)"

    def _action_type(self, key: str, move_states: dict[str, MoveState]) -> str:
        """Determine action type for a state."""
        for ms in move_states.values():
            if ms.state_key == key:
                directions = [t.strip() for t in ms.direction.split("|")]
                dir_text = ", ".join(directions)
                return f"type: movement ({dir_text})"
        return "type: transition"

    def _direction_for_state(self, key: str, move_states: dict[str, MoveState]) -> str:
        """Get direction string for a movement state."""
        for ms in move_states.values():
            if ms.state_key == key:
                directions = [t.strip() for t in ms.direction.split("|")]
                return ", ".join(directions) if directions else "unspecified"
        return "unspecified"
