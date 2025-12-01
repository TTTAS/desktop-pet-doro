"""Bootstrap routines for preparing application dependencies before UI starts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore

from .core.state import GifRepository, MoveStateRepository, StateRepository, StateService
from .core.state import TransitionStateRepository
from .utils.config_manager import ConfigManager
from .utils.paths import ACTION_TRANSITION_DIR, CLICK_ACTIONS_PATH, MOVE_DIR, PROMPT_PATH, STATE_DIR


class BootstrapError(RuntimeError):
    """Raised when bootstrapping the application fails."""


@dataclass
class BootstrappedDependencies:
    """Container for dependencies that must be prepared before UI assembly."""

    config: QtCore.QSettings  # Legacy - use config_manager instead
    config_manager: ConfigManager  # New: Type-safe configuration access
    state_service: StateService
    default_idle_gif: Path
    prompt_file_path: Path
    click_actions_path: Path


def _ensure_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - defensive guardrail
        raise BootstrapError(f"Failed to create directory: {path}") from exc


def bootstrap_environment() -> BootstrappedDependencies:
    """Prepare filesystem, configuration, and state service for the app.

    This function is intentionally side-effectful (filesystem, settings) and is
    expected to run before any UI components are constructed. Keeping this logic
    outside the UI layer makes startup easier to test and reason about.
    """

    state_storage_dir = STATE_DIR
    move_storage_dir = MOVE_DIR
    transition_action_dir = ACTION_TRANSITION_DIR

    _ensure_directory(state_storage_dir)
    _ensure_directory(move_storage_dir)
    _ensure_directory(transition_action_dir)

    default_idle_gif = state_storage_dir / "idle.gif"
    prompt_path = PROMPT_PATH
    click_actions_path = CLICK_ACTIONS_PATH

    # Create configuration (both legacy and new)
    config = QtCore.QSettings("doro-pet", "doro")
    config_manager = ConfigManager()  # Uses same QSettings location

    if not config.contains("state/idle/gif_path") and default_idle_gif.is_file():
        config.setValue("state/idle/gif_path", str(default_idle_gif))

    gif_repo = GifRepository(STATE_DIR)
    state_repo = StateRepository(STATE_DIR / "states.json")
    move_repo = MoveStateRepository(STATE_DIR / "move_states.json")
    transition_repo = TransitionStateRepository(transition_action_dir / "transitions.json")

    state_service = StateService(
        state_repo,
        move_repo,
        gif_repo,
        STATE_DIR / "state_list.txt",
        transition_repo,
    )

    return BootstrappedDependencies(
        config=config,  # Legacy - kept for backward compatibility
        config_manager=config_manager,  # New: Type-safe config access
        state_service=state_service,
        default_idle_gif=default_idle_gif,
        prompt_file_path=prompt_path,
        click_actions_path=click_actions_path,
    )
