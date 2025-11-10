"""State persistence layer - handles all file I/O for states and GIFs."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state_models import MoveState, State, VisualConfig


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

    def store_gif(self, source_path: Path, state_key: str, variant: bool = False) -> Optional[str]:
        """
        Copy a GIF into storage.

        Args:
            source_path: Source GIF file
            state_key: State this GIF belongs to
            variant: If True, store in variants subdirectory

        Returns:
            Resource ID (relative path) or None if failed
        """
        if not source_path.is_file():
            return None

        if variant:
            dest_dir = self._variant_dir(state_key)
            dest_dir.mkdir(parents=True, exist_ok=True)
            # Generate unique name for variant
            counter = 1
            dest_path = dest_dir / source_path.name
            while dest_path.exists():
                stem = source_path.stem
                dest_path = dest_dir / f"{stem}_{counter}.gif"
                counter += 1
        else:
            dest_path = self._primary_path(state_key)

        try:
            shutil.copy2(source_path, dest_path)
            return self._to_resource_id(dest_path)
        except OSError:
            return None

    def get_path(self, resource_id: str) -> Optional[Path]:
        """
        Resolve resource ID to actual file path.

        Returns:
            Absolute path if file exists, None otherwise
        """
        path = self.storage_dir / resource_id
        if path.is_file():
            try:
                return path.resolve()
            except OSError:
                return path
        return None

    def delete(self, resource_id: str) -> bool:
        """Delete a GIF by resource ID."""
        path = self.get_path(resource_id)
        if not path:
            return False

        try:
            path.unlink()
            # Clean up empty variant directory
            if path.parent != self.storage_dir and not list(path.parent.iterdir()):
                path.parent.rmdir()
            return True
        except OSError:
            return False

    def list_variants(self, state_key: str) -> list[str]:
        """List all variant resource IDs for a state."""
        variant_dir = self._variant_dir(state_key)
        if not variant_dir.is_dir():
            return []

        variants = []
        for path in sorted(variant_dir.glob("*.gif")):
            resource_id = self._to_resource_id(path)
            if resource_id:
                variants.append(resource_id)
        return variants

    def _primary_path(self, state_key: str) -> Path:
        """Get primary GIF path for a state."""
        safe_key = self._sanitize_key(state_key)
        return self.storage_dir / f"{safe_key}.gif"

    def _variant_dir(self, state_key: str) -> Path:
        """Get variants directory for a state."""
        safe_key = self._sanitize_key(state_key)
        return self.storage_dir / f"{safe_key}_variants"

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
            Dict of state_key -> State
        """
        if not self.config_path.is_file():
            return {}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        states = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                state = self._from_dict(key, value)
                states[key] = state
            except (KeyError, ValueError, TypeError):
                continue

        return states

    def save_all(self, states: dict[str, State], protected_keys: set[str]) -> bool:
        """
        Save custom states to JSON.

        Args:
            states: All states
            protected_keys: Keys to exclude from save (built-in states)

        Returns:
            True if successful
        """
        # Only save custom states
        custom_states = {
            key: self._to_dict(state)
            for key, state in states.items()
            if key not in protected_keys
        }

        try:
            if custom_states:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps(custom_states, indent=2, ensure_ascii=False)
                self.config_path.write_text(content, encoding="utf-8")
            else:
                # No custom states, remove file
                if self.config_path.exists():
                    self.config_path.unlink()
            return True
        except OSError:
            return False

    def _to_dict(self, state: State) -> dict:
        """Convert State to JSON-serializable dict."""
        return {
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

    def _from_dict(self, key: str, data: dict) -> State:
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

        return State(key=key, label=label, name_tag=name_tag, visual=visual)


class MoveStateRepository:
    """Manages movement state persistence."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_all(self) -> dict[str, MoveState]:
        """Load movement states from JSON."""
        if not self.config_path.is_file():
            return {}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {}

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

    def save_all(self, move_states: dict[str, MoveState]) -> bool:
        """Save movement states to JSON."""
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
            return True
        except OSError:
            return False


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
        gif_repo: GifRepository,
        movement_only_keys: set[str],
    ) -> str:
        """
        Generate and write state list summary.

        Returns:
            The generated text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的狀態為:"]

        # Regular states
        visible_keys = sorted(k for k in states.keys() if k not in movement_only_keys)
        for key in visible_keys:
            state = states[key]
            gif_info = self._gif_summary(state, gif_repo)
            action_type = self._action_type(key, move_states)
            lines.append(f"- ({key}) {state.label} | {action_type} | GIF: {gif_info}")

        # Movement-only states
        movement_keys = sorted(movement_only_keys)
        if movement_keys:
            lines.append("")
            lines.append("移動專用狀態:")
            for key in movement_keys:
                state = states.get(key)
                if not state:
                    continue
                gif_info = self._gif_summary(state, gif_repo)
                direction = self._direction_for_state(key, move_states)
                lines.append(f"- ({key}) {state.label} | type: movement ({direction}) | GIF: {gif_info}")

        output = "\n".join(lines) + "\n"

        try:
            self.output_path.write_text(output, encoding="utf-8")
        except OSError:
            pass

        return output.strip()

    def _gif_summary(self, state: State, gif_repo: GifRepository) -> str:
        """Generate GIF summary string."""
        if not state.primary_gif_id:
            return "(no GIF)"

        primary_path = gif_repo.get_path(state.primary_gif_id)
        gif_info = str(primary_path) if primary_path else "(no GIF)"

        variant_count = len(state.variant_gif_ids)
        if variant_count > 0:
            gif_info += f" (+{variant_count} variants)"

        return gif_info

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
