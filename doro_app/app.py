"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from .bootstrap import BootstrappedDependencies, bootstrap_environment
from .constants import MOVEMENT_STEP_PX
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .core.core_manager import CoreManager
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

        # ═════════════════════════════════════════════════════════════
        # Phase 1: Create Business Logic Layer Components
        # (No UI dependencies - can be tested independently)
        # ═════════════════════════════════════════════════════════════

        # Transition player (no window dependency)
        self._transition_player = TransitionPlayer(state_service=self._state_service)

        # Bubble controller (no window dependency)
        self._bubble_controller = BubbleController(
            config_manager=self._config_manager,
        )

        # Chat components
        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=None,  # Will be set after state_controller is created
            movement_hint_provider=None,  # Will be set after movement is created
            parent=None,  # No parent needed
            config_manager=self._config_manager,
        )

        # NOTE: MovementManager still needs window reference via Protocol
        # This will be created after Window is instantiated

        # ═════════════════════════════════════════════════════════════
        # Phase 2: Create Window (UI layer composition root)
        # ═════════════════════════════════════════════════════════════

        self.window = DoroWindow(
            state_service=self._state_service,
            config=self._config,  # Legacy
            not_topmost=not_topmost,
            config_manager=self._config_manager,  # New: Type-safe config
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 3: Create UI Controllers
        # ═════════════════════════════════════════════════════════════

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

        # Now create movement manager with window (Protocol dependency)
        self._movement = MovementManager(
            window=self.window,
            state_service=self._state_service,
            movement_step_px=MOVEMENT_STEP_PX
        )

        # Update chat controller providers now that dependencies are available
        self._chat_controller._state_text_provider = lambda: self._state_controller.get_state_list_text()
        self._chat_controller._movement_hint_provider = lambda: self._movement.instruction_text()

        # Create chat orchestrator
        self._chat_orchestrator = ChatOrchestrator(
            self._chat_controller,
            self._movement,
            self._state_service,
        )

        # Create click action controller
        self._click_action_controller = ClickActionController(
            actions_file=self._click_actions_path,
            chat_orchestrator=self._chat_orchestrator,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 4: Create CoreManager (Business Logic Coordinator)
        # ═════════════════════════════════════════════════════════════

        self.core_manager = CoreManager(
            state_service=self._state_service,
            chat_controller=self._chat_controller,
            chat_orchestrator=self._chat_orchestrator,
            movement_manager=self._movement,
            transition_player=self._transition_player,
            config_manager=self._config_manager,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 5: Wire Components (Connect all layers)
        # ═════════════════════════════════════════════════════════════

        self._connect_business_to_ui()
        self._connect_ui_controllers()

        # ═════════════════════════════════════════════════════════════
        # Phase 6: Wire remaining UI-specific dependencies
        # ═════════════════════════════════════════════════════════════
        # TODO: Move this logic to DoroApp and remove wire_dependencies entirely
        self.window.wire_dependencies(
            state_controller=self._state_controller,
            gif_controller=self._gif_controller,
            dialog_manager=self._dialog_manager,
            click_action_controller=self._click_action_controller,
            bubble_controller=self._bubble_controller,
        )

        # ─────────────────────────────────────────────────────────
        # Initialize StateService and restore last state
        # ─────────────────────────────────────────────────────────
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        # Use ConfigManager for type-safe config access
        saved_state_key = self._config_manager.app.current_state
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

    def _connect_business_to_ui(self):
        """Connect business logic layer (CoreManager) to UI layer (Window)."""

        # ─────────────────────────────────────────────────────────
        # CoreManager → Window connections
        # ─────────────────────────────────────────────────────────

        # Bubble text requests from core → window
        self.core_manager.bubble_text_requested.connect(
            lambda text, kwargs: self._bubble_controller.set_text(text, **kwargs)
        )
        self.core_manager.bubble_clear_requested.connect(
            self._bubble_controller.clear_text
        )

        # Cursor management
        self.core_manager.busy_cursor_requested.connect(
            lambda enabled: self.window.set_busy_cursor(enabled) if hasattr(self.window, 'set_busy_cursor') else None
        )

        # Notifications
        self.core_manager.notification_requested.connect(
            lambda severity, title, msg: self._dialog_manager.show_notification(severity, title, msg)
        )

        # Transition signals from core → window
        self.core_manager.transition_gif_ready.connect(
            self.window._on_transition_movie_loaded
        )
        self.core_manager.transition_completed.connect(
            self.window._on_transition_completed
        )
        self.core_manager.load_state_gif_requested.connect(
            self.window._load_state_gif
        )

        # ─────────────────────────────────────────────────────────
        # BubbleController → Window connections
        # ─────────────────────────────────────────────────────────

        self._bubble_controller.text_changed.connect(
            lambda text, show_override: self.window._on_bubble_text_changed(text, show_override)
        )
        self._bubble_controller.visibility_changed.connect(
            lambda visible: self.window._on_bubble_visibility_changed(visible)
        )
        self._bubble_controller.offset_changed.connect(
            lambda offset: self.window._on_bubble_offset_changed(offset)
        )
        self._bubble_controller.scale_changed.connect(
            lambda scale: self.window._on_bubble_scale_changed(scale)
        )
        self._bubble_controller.repaint_requested.connect(
            self.window.update
        )
        self._bubble_controller.cursor_unset_requested.connect(
            self.window.unsetCursor
        )
        self._bubble_controller.update_bubble_side_requested.connect(
            lambda: self.window._update_bubble_side_from_offset() if hasattr(self.window, '_update_bubble_side_from_offset') else None
        )
        self._bubble_controller.state_settings_apply_requested.connect(
            lambda state_key: self._state_controller.apply_state_settings(state_key)
        )

        # ─────────────────────────────────────────────────────────
        # Window → CoreManager connections
        # ─────────────────────────────────────────────────────────

        # State changes from StateController → CoreManager
        self._state_controller.state_changed.connect(
            self.core_manager.on_state_changed
        )

        # User click → CoreManager
        # (Window will need a user_clicked signal that we connect here)

        # Movement tick → CoreManager
        # (Window's tick timer will call core_manager.process_movement_tick)

    def _connect_ui_controllers(self):
        """Connect UI controllers to Window (legacy connections that remain in Window)."""

        # Note: These connections are for UI controllers that still need to interact
        # with Window directly. Eventually these should also be refactored.

        # StateController → Window
        self._state_controller.state_changed.connect(
            self.window._on_controller_state_changed
        )

        # GifController signals (if any)
        # DialogManager doesn't emit signals to Window

        # ClickActionController → Window
        # (Window's click event will call click_action_controller.handle_click)

        # Store references in Window for backward compatibility
        # Only UI controllers and CoreManager are stored
        self.window._state_controller = self._state_controller
        self.window._gif_controller = self._gif_controller
        self.window._dialog_manager = self._dialog_manager
        self.window._click_action_controller = self._click_action_controller
        self.window._bubble_controller = self._bubble_controller
        self.window._core_manager = self.core_manager
        # NOTE: _chat_controller, _movement, _chat_orchestrator removed
        # Access these through _core_manager instead

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()
