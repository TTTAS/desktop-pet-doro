"""Core business logic manager - coordinates all domain layer components.

This is the composition root for the business logic layer.
It manages and coordinates all core services without any UI dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .chat.controller import ChatController
    from .chat.orchestrator import ChatOrchestrator
    from .movement.manager import MovementManager
    from .state import StateService
    from .state.transition_player import TransitionPlayer
    from ..utils.config_manager import ConfigManager

logger = get_logger(__name__)


class CoreManager(QtCore.QObject):
    """
    Business logic layer manager.

    Responsibilities:
    - Manage all core business logic components
    - Coordinate interactions between them
    - Provide unified API to external layers (UI)
    - Emit signals to notify UI layer

    Does NOT contain:
    - Any UI-related logic
    - Any Qt Widgets
    - Direct references to Window
    """

    # ═══════════════════════════════════════════════════════════
    # Signals for UI layer (outbound)
    # ═══════════════════════════════════════════════════════════

    # Chat signals
    bubble_text_requested = QtCore.Signal(str, dict)  # text, kwargs
    bubble_clear_requested = QtCore.Signal()
    busy_cursor_requested = QtCore.Signal(bool)  # enabled
    notification_requested = QtCore.Signal(str, str, str)  # severity, title, message

    # Transition signals
    transition_gif_ready = QtCore.Signal(object, QtCore.QSize)  # QMovie, sprite_size
    transition_completed = QtCore.Signal(str)  # target_state_key
    load_state_gif_requested = QtCore.Signal(str)  # state_key

    # Movement signals (if needed)
    movement_completed = QtCore.Signal()

    def __init__(
        self,
        state_service: StateService,
        chat_controller: ChatController,
        chat_orchestrator: ChatOrchestrator,
        movement_manager: MovementManager,
        transition_player: TransitionPlayer,
        config_manager: ConfigManager,
    ):
        """
        Initialize CoreManager with all business logic components.

        Args:
            state_service: State management service
            chat_controller: Chat interaction controller
            chat_orchestrator: Chat coordination layer
            movement_manager: Movement logic manager
            transition_player: State transition player
            config_manager: Configuration manager
        """
        super().__init__()

        logger.info("Initializing CoreManager")

        # ═══════════════════════════════════════════════════════════
        # Business logic components (held by CoreManager)
        # ═══════════════════════════════════════════════════════════

        self._state_service = state_service
        self._chat_controller = chat_controller
        self._chat_orchestrator = chat_orchestrator
        self._movement = movement_manager
        self._transition_player = transition_player
        self._config_manager = config_manager

        # Track previous state for transition detection
        self._previous_state_key: str | None = None

        # ═══════════════════════════════════════════════════════════
        # Connect internal components
        # ═══════════════════════════════════════════════════════════

        self._connect_internal_components()

    def _connect_internal_components(self):
        """Connect business logic components internally."""

        # Chat orchestrator signals → Forward to UI
        self._chat_orchestrator.bubble_text_requested.connect(self.bubble_text_requested)
        self._chat_orchestrator.bubble_clear_requested.connect(self.bubble_clear_requested)
        self._chat_orchestrator.busy_cursor_requested.connect(self.busy_cursor_requested)
        self._chat_orchestrator.notification_requested.connect(self.notification_requested)

        # Transition player signals → Forward to UI
        self._transition_player.transition_movie_loaded.connect(self.transition_gif_ready)
        self._transition_player.transition_completed.connect(self._on_transition_completed)

        logger.debug("CoreManager internal components connected")

    # ═══════════════════════════════════════════════════════════
    # Public API - Called by UI layer or App
    # ═══════════════════════════════════════════════════════════

    def on_state_changed(self, state_key: str) -> bool:
        """
        Handle state change notification from UI.

        Args:
            state_key: New state key

        Returns:
            True if transition is playing, False if should load GIF directly
        """
        old_state = self._previous_state_key
        self._previous_state_key = state_key

        # Skip on initial load
        if old_state is None:
            logger.debug(f"Initial state load: {state_key}")
            self.load_state_gif_requested.emit(state_key)
            return False

        # Skip if same state
        if old_state == state_key:
            logger.debug(f"Same state, no change needed: {state_key}")
            return False

        # Try to play transition
        logger.debug(f"State changed: {old_state} -> {state_key}")
        if self._transition_player.play_transition(old_state, state_key):
            logger.debug(f"Playing transition: {old_state} -> {state_key}")
            return True
        else:
            logger.debug(f"No transition, loading GIF directly: {state_key}")
            self.load_state_gif_requested.emit(state_key)
            return False

    def send_chat_message(self, message: str, *, silent: bool = False, is_auto: bool = False):
        """
        Send chat message (called by UI).

        Args:
            message: User message
            silent: If True, suppress notifications
            is_auto: If True, this is an automatic message
        """
        self._chat_orchestrator.send_message(message, silent=silent, is_auto=is_auto)

    def on_user_clicked(self):
        """Handle user click event (called by UI)."""
        # Trigger random action if click action controller is available
        logger.debug("User clicked")

    def process_movement_tick(self, dt: float):
        """
        Process movement animation tick.

        Args:
            dt: Delta time in seconds
        """
        self._movement.process_active_movement(dt)

    # ═══════════════════════════════════════════════════════════
    # Internal event handlers
    # ═══════════════════════════════════════════════════════════

    def _on_transition_completed(self, target_state_key: str):
        """
        Handle transition completion.

        Args:
            target_state_key: Target state to load after transition
        """
        logger.debug(f"Transition completed, loading target state: {target_state_key}")
        # Request UI to load the target state GIF
        self.load_state_gif_requested.emit(target_state_key)
        # Also emit the transition_completed signal for UI
        self.transition_completed.emit(target_state_key)

    # ═══════════════════════════════════════════════════════════
    # Properties for external access (read-only)
    # ═══════════════════════════════════════════════════════════

    @property
    def state_service(self) -> StateService:
        """Get StateService (read-only access)."""
        return self._state_service

    @property
    def chat_orchestrator(self) -> ChatOrchestrator:
        """Get ChatOrchestrator (read-only access)."""
        return self._chat_orchestrator

    @property
    def movement_manager(self) -> MovementManager:
        """Get MovementManager (read-only access)."""
        return self._movement

    @property
    def is_chat_inflight(self) -> bool:
        """Check if chat request is in progress."""
        return self._chat_orchestrator.is_inflight
