"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from .constants import MOVEMENT_STEP_PX
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .core.movement.manager import MovementManager
from .core.state import GifRepository, MoveStateRepository, StateRepository, TransitionStateRepository
from .core.state import StateService
from .core.state.transition_player import TransitionPlayer
from .ui.components.bubble_controller import BubbleController
from .ui.window import DoroWindow
from .utils.paths import ACTION_TRANSITION_DIR, CLICK_ACTIONS_PATH, MOVE_DIR, PROMPT_PATH, STATE_DIR


class DoroApp:
    """
    Application composition root.

    Responsible for:
    - Creating and managing all application directories
    - Assembling all services and dependencies
    - Wiring components together
    - Creating the main window

    This separates assembly logic from the UI layer (DoroWindow).
    """

    def __init__(self, not_topmost: bool = False):
        """
        Initialize the application.

        Args:
            not_topmost: If True, window will not stay on top
        """
        # ─────────────────────────────────────────────────────────
        # 1. Create application directories
        # ─────────────────────────────────────────────────────────
        self._state_storage_dir = STATE_DIR
        self._state_storage_dir.mkdir(parents=True, exist_ok=True)

        self._move_storage_dir = MOVE_DIR
        self._move_storage_dir.mkdir(parents=True, exist_ok=True)

        self._transition_action_dir = ACTION_TRANSITION_DIR
        self._transition_action_dir.mkdir(parents=True, exist_ok=True)

        # Define file paths
        self._default_idle_gif = self._state_storage_dir / "idle.gif"
        self._state_list_path = self._state_storage_dir / "state_list.txt"
        self._move_state_list_path = self._state_storage_dir / "move_state_list.txt"
        self._state_config_path = self._state_storage_dir / "states.json"
        self._prompt_file_path = PROMPT_PATH
        self._click_actions_path = CLICK_ACTIONS_PATH

        # ─────────────────────────────────────────────────────────
        # 2. Create QSettings (configuration management)
        # ─────────────────────────────────────────────────────────
        self._config = QtCore.QSettings("doro-pet", "doro")

        # Write default idle.gif once (if user hasn't set any)
        if not self._config.contains("state/idle/gif_path") and self._default_idle_gif.is_file():
            self._config.setValue("state/idle/gif_path", str(self._default_idle_gif))

        # ─────────────────────────────────────────────────────────
        # 3. Create Repositories (data layer)
        # ─────────────────────────────────────────────────────────
        gif_repo = GifRepository(STATE_DIR)
        state_repo = StateRepository(STATE_DIR / "states.json")
        move_repo = MoveStateRepository(STATE_DIR / "move_states.json")
        transition_repo = TransitionStateRepository(ACTION_TRANSITION_DIR / "transitions.json")

        # ─────────────────────────────────────────────────────────
        # 4. Create StateService (core business logic)
        # ─────────────────────────────────────────────────────────
        self._state_service = StateService(
            state_repo,
            move_repo,
            gif_repo,
            STATE_DIR / "state_list.txt",
            transition_repo,
        )

        # ─────────────────────────────────────────────────────────
        # 5. Create Window first (needed by managers due to circular deps)
        # ─────────────────────────────────────────────────────────
        # NOTE: This is temporary. In Phase 3, managers won't need window reference.
        self.window = DoroWindow(
            state_service=self._state_service,
            config=self._config,
            not_topmost=not_topmost,
        )

        # ─────────────────────────────────────────────────────────
        # 6. Create Managers (need window reference - circular dependency)
        # ─────────────────────────────────────────────────────────
        self._transition_player = TransitionPlayer(self.window, self._state_service)
        self._bubble_controller = BubbleController(self.window)
        self._movement = MovementManager(self.window, self._state_service, MOVEMENT_STEP_PX)

        # ─────────────────────────────────────────────────────────
        # 7. Create Chat components
        # ─────────────────────────────────────────────────────────
        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=lambda: self.window.state_list_text,
            movement_hint_provider=lambda: self._movement.instruction_text(),
            parent=self.window,
        )
        self._chat_orchestrator = ChatOrchestrator(
            self._chat_controller,
            self._movement,
            self._state_service,
        )

        # ─────────────────────────────────────────────────────────
        # 8. Wire dependencies into Window
        # ─────────────────────────────────────────────────────────
        self.window.wire_dependencies(
            transition_player=self._transition_player,
            bubble_controller=self._bubble_controller,
            movement_manager=self._movement,
            chat_controller=self._chat_controller,
            chat_orchestrator=self._chat_orchestrator,
        )

        # ─────────────────────────────────────────────────────────
        # 9. Initialize StateService and restore last state
        # ─────────────────────────────────────────────────────────
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        saved_state_key = self._config.value("current_state", "idle")
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()
