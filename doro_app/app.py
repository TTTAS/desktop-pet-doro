"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from .bootstrap import BootstrappedDependencies, bootstrap_environment
from .constants import MOVEMENT_STEP_PX
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .core.movement.manager import MovementManager
from .core.state import StateService
from .core.state.transition_player import TransitionPlayer
from .ui.components.bubble_controller import BubbleController
from .ui.controllers import ClickActionController, DialogManager, GifController, StateController
from .ui.window import DoroWindow


class DoroApp:
    """
    Application composition root.

    Responsible for:
    - Assembling all services and dependencies
    - Wiring components together
    - Creating the main window

    This separates assembly logic from the UI layer (DoroWindow).
    """

    def __init__(
        self,
        not_topmost: bool = False,
        deps: BootstrappedDependencies | None = None,
    ):
        """
        Initialize the application.

        Args:
            not_topmost: If True, window will not stay on top
        """
        deps = deps or bootstrap_environment()

        self._config = deps.config  # Legacy QSettings
        self._config_manager = deps.config_manager  # New ConfigManager
        self._state_service: StateService = deps.state_service
        self._default_idle_gif = deps.default_idle_gif
        self._prompt_file_path = deps.prompt_file_path
        self._click_actions_path = deps.click_actions_path

        # ─────────────────────────────────────────────────────────
        # Create Window first (needed by managers due to circular deps)
        # ─────────────────────────────────────────────────────────
        # NOTE: Window is created before controllers because some controllers
        # need window reference. This will be fixed in Phase 3.
        self.window = DoroWindow(
            state_service=self._state_service,
            config=self._config,  # Legacy
            not_topmost=not_topmost,
            config_manager=self._config_manager,  # New: Type-safe config
        )

        # ─────────────────────────────────────────────────────────
        # Create UI Controllers (coordinate between services and UI)
        # ─────────────────────────────────────────────────────────
        self._state_controller = StateController(
            state_service=self._state_service,
            view_model=self.window.view_model,
            config=self._config,  # Legacy
            config_manager=self._config_manager,  # New: Type-safe config
        )
        self._gif_controller = GifController(view_model=self.window.view_model)
        self._dialog_manager = DialogManager(
            parent_window=self.window,
            state_service=self._state_service,
        )

        # ─────────────────────────────────────────────────────────
        # Create Managers (need window reference - circular dependency)
        # ─────────────────────────────────────────────────────────
        self._transition_player = TransitionPlayer(self.window, self._state_service)
        self._bubble_controller = BubbleController(
            self.window,
            config_manager=self._config_manager,  # Type-safe config access
        )
        self._movement = MovementManager(self.window, self._state_service, MOVEMENT_STEP_PX)

        # ─────────────────────────────────────────────────────────
        # Create Chat components
        # ─────────────────────────────────────────────────────────
        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=lambda: self._state_controller.get_state_list_text(),
            movement_hint_provider=lambda: self._movement.instruction_text(),
            parent=self.window,
            config_manager=self._config_manager,
        )
        self._chat_orchestrator = ChatOrchestrator(
            self._chat_controller,
            self._movement,
            self._state_service,
        )

        # Create ClickActionController after ChatOrchestrator
        self._click_action_controller = ClickActionController(
            actions_file=self._click_actions_path,
            chat_orchestrator=self._chat_orchestrator,
        )

        # ─────────────────────────────────────────────────────────
        # Wire all dependencies into Window
        # ─────────────────────────────────────────────────────────
        self.window.wire_dependencies(
            state_controller=self._state_controller,
            gif_controller=self._gif_controller,
            dialog_manager=self._dialog_manager,
            click_action_controller=self._click_action_controller,
            transition_player=self._transition_player,
            bubble_controller=self._bubble_controller,
            movement_manager=self._movement,
            chat_controller=self._chat_controller,
            chat_orchestrator=self._chat_orchestrator,
        )

        # ─────────────────────────────────────────────────────────
        # Initialize StateService and restore last state
        # ─────────────────────────────────────────────────────────
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        # Use ConfigManager for type-safe config access
        saved_state_key = self._config_manager.app.current_state
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()
