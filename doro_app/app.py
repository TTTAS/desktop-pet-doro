"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from .bootstrap import BootstrappedDependencies, bootstrap_environment
from .constants import (
    BUBBLE_AUTO_HIDE_MS,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
    CLICK_DRAG_THRESHOLD_PX,
    MOVEMENT_STEP_PX,
)
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .core.core_manager import CoreManager
from .core.movement.manager import MovementManager
from .core.state import StateService
from .core.state.transition_player import TransitionPlayer
from .ui.components.bubble_controller import BubbleConfig, BubbleController
from .ui.controllers import ClickActionController, DialogManager, GifController, StateController
from .ui.events.mouse_event_handler import MouseEventHandler
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
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=None,  # Will be set after state_controller is created
            movement_hint_provider=None,  # Will be set after movement is created
            config_manager=self._config_manager,
            parent=None,  # No parent needed
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

        # ─────────────────────────────────────────────────────────
        # Initialize StateService and restore last state
        # ─────────────────────────────────────────────────────────
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        # Use ConfigManager for type-safe config access
        saved_state_key = self._config_manager.app.current_state
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

    def _connect_business_to_ui(self):
        """Translate domain events to UI operations (Application Layer responsibility)."""

        # ═════════════════════════════════════════════════════════════
        # Domain Events → UI Operations (Translation Layer)
        # ═════════════════════════════════════════════════════════════

        # Chat domain events
        self.core_manager.chat_response_received.connect(
            self._on_chat_response_received
        )
        self.core_manager.chat_operation_started.connect(
            self._on_chat_operation_started
        )
        self.core_manager.chat_operation_completed.connect(
            self._on_chat_operation_completed
        )
        self.core_manager.chat_error_occurred.connect(
            self._on_chat_error_occurred
        )

        # State domain events
        self.core_manager.state_changed.connect(
            self._on_domain_state_changed
        )

        # Transition domain events
        self.core_manager.transition_completed.connect(
            self._on_domain_transition_completed
        )

        # TransitionPlayer → Window (UI-specific signal for playing GIF)
        self._transition_player.transition_movie_loaded.connect(
            self.window.on_transition_movie_loaded
        )

        # ═════════════════════════════════════════════════════════════
        # BubbleController → Window connections (UI Layer internal)
        # ═════════════════════════════════════════════════════════════

        self._bubble_controller.text_changed.connect(
            lambda text, show_override: self.window.on_bubble_text_changed(text, show_override)
        )
        self._bubble_controller.visibility_changed.connect(
            lambda visible: self.window.on_bubble_visibility_changed(visible)
        )
        self._bubble_controller.offset_changed.connect(
            lambda offset: self.window.on_bubble_offset_changed(offset)
        )
        self._bubble_controller.scale_changed.connect(
            lambda scale: self.window.on_bubble_scale_changed(scale)
        )
        self._bubble_controller.repaint_requested.connect(
            self.window.update
        )
        self._bubble_controller.cursor_unset_requested.connect(
            self.window.unsetCursor
        )
        self._bubble_controller.update_bubble_side_requested.connect(
            self.window.update_bubble_side_from_offset
        )
        self._bubble_controller.state_settings_apply_requested.connect(
            lambda state_key: self._state_controller.apply_state_settings(state_key)
        )

        # ═════════════════════════════════════════════════════════════
        # UI → Business Logic (Upward calls - allowed)
        # ═════════════════════════════════════════════════════════════

        # State changes from StateController → CoreManager
        self._state_controller.state_changed.connect(
            self.core_manager.on_state_changed
        )

        # User click → CoreManager
        # (Window will need a user_clicked signal that we connect here)

        # Movement tick → CoreManager
        # (Window's tick timer will call core_manager.process_movement_tick)

    # ═════════════════════════════════════════════════════════════
    # Domain Event Translation Methods (Application Layer)
    # ═════════════════════════════════════════════════════════════

    def _on_chat_response_received(self, response_text: str, kwargs: dict):
        """Translate chat response domain event to UI bubble display."""
        self._bubble_controller.set_text(
            response_text,
            override_visibility=kwargs.get("override_visibility", False),
            auto_hide=kwargs.get("auto_hide", True),
            hide_delay_ms=kwargs.get("hide_delay_ms", 6000),
        )

    def _on_chat_operation_started(self):
        """Translate chat operation started domain event to UI busy cursor."""
        self.window.set_busy_cursor(True)

    def _on_chat_operation_completed(self):
        """Translate chat operation completed domain event to UI cursor reset."""
        self.window.set_busy_cursor(False)

    def _on_chat_error_occurred(self, error_message: str):
        """Translate chat error domain event to UI notification."""
        self._dialog_manager.show_notification(
            severity="error",
            title="聊天錯誤",
            message=error_message
        )

    def _on_domain_state_changed(self, state_key: str):
        """Translate state changed domain event to UI GIF loading."""
        self.window.current_state_key = state_key
        self.window.load_state_gif(state_key)

    def _on_domain_transition_completed(self, target_state_key: str):
        """Translate transition completed domain event to UI transition completion."""
        self.window.current_state_key = target_state_key
        self.window.on_transition_completed(target_state_key)

    def _connect_ui_controllers(self):
        """Connect UI controllers to Window and wire all UI-layer dependencies."""

        # ─────────────────────────────────────────────────────────
        # Create mouse event handler
        # ─────────────────────────────────────────────────────────
        mouse_handler = MouseEventHandler(
            bubble_controller=self._bubble_controller,
            click_threshold=CLICK_DRAG_THRESHOLD_PX,
        )

        # ─────────────────────────────────────────────────────────
        # Inject all controllers into Window via public API
        # ─────────────────────────────────────────────────────────
        self.window.inject_controllers(
            state_controller=self._state_controller,
            gif_controller=self._gif_controller,
            dialog_manager=self._dialog_manager,
            click_action_controller=self._click_action_controller,
            bubble_controller=self._bubble_controller,
            core_manager=self.core_manager,
            mouse_handler=mouse_handler,
        )

        # ─────────────────────────────────────────────────────────
        # Wire mouse event handler signals
        # ─────────────────────────────────────────────────────────
        mouse_handler.window_drag_requested.connect(self.window.move)
        mouse_handler.click_detected.connect(
            lambda: (
                self.window.mark_user_activity(),
                self._click_action_controller.trigger_random_action(),
            )
        )
        mouse_handler.user_activity_detected.connect(
            self.window.mark_user_activity
        )

        # ─────────────────────────────────────────────────────────
        # Connect UI controller signals → Window
        # ─────────────────────────────────────────────────────────
        self._state_controller.repaint_requested.connect(self.window.update)
        self._state_controller.state_list_updated.connect(
            self.window.on_state_list_updated
        )

        self._gif_controller.repaint_requested.connect(self.window.update)
        self._gif_controller.gif_loaded.connect(self.window.on_gif_loaded)
        self._gif_controller.sprite_size_changed.connect(
            self.window.on_sprite_size_changed
        )

        # ─────────────────────────────────────────────────────────
        # Apply persisted bubble configuration
        # ─────────────────────────────────────────────────────────
        self._bubble_controller.apply_persisted_config(
            BubbleConfig(
                offset_x=self._config_manager.ui.bubble_offset_x,
                offset_y=self._config_manager.ui.bubble_offset_y,
                scale=self._config_manager.ui.bubble_scale,
                auto_hide_ms=BUBBLE_AUTO_HIDE_MS,
            )
        )

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()
