"""Tests for CoreManager - the business logic layer coordinator."""

from unittest.mock import Mock, MagicMock, patch, call
import pytest
from PySide6.QtCore import QObject, Signal

from doro_app.core.core_manager import CoreManager


@pytest.fixture
def mock_state_service():
    """Create mock StateService."""
    service = Mock()
    service.get_state.return_value = Mock(key="idle")
    return service


@pytest.fixture
def mock_chat_controller():
    """Create mock ChatController."""
    controller = Mock(spec=QObject)
    # Add Qt Signal attributes
    controller.request_started = Mock()
    controller.request_succeeded = Mock()
    controller.request_failed = Mock()
    return controller


@pytest.fixture
def mock_chat_orchestrator():
    """Create mock ChatOrchestrator."""
    orchestrator = Mock(spec=QObject)
    # Mock Qt Signals
    orchestrator.bubble_text_requested = Mock()
    orchestrator.bubble_text_requested.connect = Mock()
    orchestrator.bubble_clear_requested = Mock()
    orchestrator.bubble_clear_requested.connect = Mock()
    orchestrator.busy_cursor_requested = Mock()
    orchestrator.busy_cursor_requested.connect = Mock()
    orchestrator.notification_requested = Mock()
    orchestrator.notification_requested.connect = Mock()

    # Mock properties
    orchestrator.is_inflight = False

    # Mock methods
    orchestrator.send_message = Mock()

    return orchestrator


@pytest.fixture
def mock_movement_manager():
    """Create mock MovementManager."""
    manager = Mock()
    manager.process_active_movement = Mock()
    return manager


@pytest.fixture
def mock_transition_player():
    """Create mock TransitionPlayer."""
    player = Mock(spec=QObject)
    # Mock Qt Signal
    player.transition_completed = Mock()
    player.transition_completed.connect = Mock()
    player.transition_movie_loaded = Mock()
    player.transition_movie_loaded.connect = Mock()

    # Mock methods
    player.play_transition = Mock(return_value=False)  # Default: no transition

    return player


@pytest.fixture
def mock_config_manager():
    """Create mock ConfigManager."""
    config = Mock()
    return config


@pytest.fixture
def core_manager(
    mock_state_service,
    mock_chat_controller,
    mock_chat_orchestrator,
    mock_movement_manager,
    mock_transition_player,
    mock_config_manager,
):
    """Create CoreManager with all mocked dependencies."""
    manager = CoreManager(
        state_service=mock_state_service,
        chat_controller=mock_chat_controller,
        chat_orchestrator=mock_chat_orchestrator,
        movement_manager=mock_movement_manager,
        transition_player=mock_transition_player,
        config_manager=mock_config_manager,
    )
    return manager


# ═══════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════


class TestCoreManagerInitialization:
    """Test CoreManager initialization and component wiring."""

    def test_initialization_succeeds(self, core_manager):
        """CoreManager can be initialized with all dependencies."""
        assert core_manager is not None

    def test_holds_all_components(
        self,
        core_manager,
        mock_state_service,
        mock_chat_orchestrator,
        mock_movement_manager,
    ):
        """CoreManager holds references to all business logic components."""
        assert core_manager.state_service is mock_state_service
        assert core_manager.chat_orchestrator is mock_chat_orchestrator
        assert core_manager.movement_manager is mock_movement_manager

    def test_a11y_service_defaults_none(self, core_manager):
        """a11y_service is optional and defaults to None."""
        assert core_manager.a11y_service is None

    def test_a11y_service_is_exposed(
        self,
        mock_state_service,
        mock_chat_controller,
        mock_chat_orchestrator,
        mock_movement_manager,
        mock_transition_player,
        mock_config_manager,
    ):
        """A passed a11y_service is exposed via the property."""
        sentinel = object()
        manager = CoreManager(
            state_service=mock_state_service,
            chat_controller=mock_chat_controller,
            chat_orchestrator=mock_chat_orchestrator,
            movement_manager=mock_movement_manager,
            transition_player=mock_transition_player,
            config_manager=mock_config_manager,
            a11y_service=sentinel,
        )
        assert manager.a11y_service is sentinel

    def test_connects_internal_components(
        self,
        mock_chat_orchestrator,
        mock_transition_player,
        core_manager,
    ):
        """CoreManager connects internal components on initialization."""
        # Verify chat orchestrator signals were connected
        mock_chat_orchestrator.bubble_text_requested.connect.assert_called()
        mock_chat_orchestrator.busy_cursor_requested.connect.assert_called()
        mock_chat_orchestrator.notification_requested.connect.assert_called()

        # Verify transition player signals were connected
        mock_transition_player.transition_completed.connect.assert_called()


# ═══════════════════════════════════════════════════════════
# State Change Tests
# ═══════════════════════════════════════════════════════════


class TestStateChangeHandling:
    """Test state change coordination."""

    def test_on_state_changed_first_load(self, core_manager):
        """First state load emits state_changed signal without transition."""
        # Connect a Mock listener to verify signal was emitted
        mock_listener = Mock()
        core_manager.state_changed.connect(mock_listener)

        result = core_manager.on_state_changed("idle")

        assert result is False  # No transition on first load
        mock_listener.assert_called_once_with("idle")

    def test_on_state_changed_same_state_no_action(self, core_manager):
        """Changing to same state does nothing."""
        # Set initial state
        core_manager.on_state_changed("idle")

        # Try to change to same state
        result = core_manager.on_state_changed("idle")

        assert result is False

    def test_on_state_changed_with_transition(
        self,
        core_manager,
        mock_transition_player,
    ):
        """State change with available transition plays transition."""
        # Set initial state
        core_manager.on_state_changed("idle")

        # Mock transition player to return True (transition available)
        mock_transition_player.play_transition.return_value = True

        # Connect Mock listener to verify signal
        mock_listener = Mock()
        core_manager.transition_started.connect(mock_listener)

        # Change state with transition
        result = core_manager.on_state_changed("walking")

        assert result is True  # Transition is playing
        mock_listener.assert_called_once_with("idle", "walking")
        mock_transition_player.play_transition.assert_called_with("idle", "walking")

    def test_on_state_changed_without_transition(
        self,
        core_manager,
        mock_transition_player,
    ):
        """State change without transition emits direct state_changed."""
        # Set initial state
        core_manager.on_state_changed("idle")

        # Mock transition player to return False (no transition)
        mock_transition_player.play_transition.return_value = False

        # Connect Mock listener to verify signal
        mock_listener = Mock()
        core_manager.state_changed.connect(mock_listener)

        # Change state without transition
        result = core_manager.on_state_changed("running")

        assert result is False  # No transition
        mock_listener.assert_called_once_with("running")


# ═══════════════════════════════════════════════════════════
# Chat Tests
# ═══════════════════════════════════════════════════════════


class TestChatOperations:
    """Test chat message sending and configuration."""

    def test_send_chat_message(self, core_manager, mock_chat_orchestrator):
        """send_chat_message delegates to chat orchestrator."""
        core_manager.send_chat_message("Hello", silent=False, is_auto=False)

        mock_chat_orchestrator.send_message.assert_called_once_with(
            "Hello", silent=False, is_auto=False
        )

    def test_send_chat_message_silent(self, core_manager, mock_chat_orchestrator):
        """Silent chat messages suppress notifications."""
        core_manager.send_chat_message("Test", silent=True, is_auto=False)

        mock_chat_orchestrator.send_message.assert_called_with(
            "Test", silent=True, is_auto=False
        )

    def test_send_chat_message_auto(self, core_manager, mock_chat_orchestrator):
        """Auto chat messages are marked as automatic."""
        core_manager.send_chat_message("Auto message", silent=False, is_auto=True)

        mock_chat_orchestrator.send_message.assert_called_with(
            "Auto message", silent=False, is_auto=True
        )

    def test_is_chat_inflight_property(self, core_manager, mock_chat_orchestrator):
        """is_chat_inflight returns orchestrator's inflight status."""
        mock_chat_orchestrator.is_inflight = True
        assert core_manager.is_chat_inflight is True

        mock_chat_orchestrator.is_inflight = False
        assert core_manager.is_chat_inflight is False


# ═══════════════════════════════════════════════════════════
# Movement Tests
# ═══════════════════════════════════════════════════════════


class TestMovementProcessing:
    """Test movement animation processing."""

    def test_process_movement_tick(self, core_manager, mock_movement_manager):
        """process_movement_tick delegates to movement manager."""
        core_manager.process_movement_tick(0.016)  # ~60fps

        mock_movement_manager.process_active_movement.assert_called_once_with(0.016)

    def test_process_movement_tick_multiple_calls(
        self,
        core_manager,
        mock_movement_manager,
    ):
        """Movement tick can be called multiple times."""
        core_manager.process_movement_tick(0.016)
        core_manager.process_movement_tick(0.020)
        core_manager.process_movement_tick(0.014)

        assert mock_movement_manager.process_active_movement.call_count == 3


# ═══════════════════════════════════════════════════════════
# Event Handler Tests
# ═══════════════════════════════════════════════════════════


class TestEventHandlers:
    """Test internal event handlers."""

    def test_transition_completed_emits_signals(self, core_manager):
        """Transition completion emits both transition_completed and state_changed."""
        # Connect Mock listeners to verify both signals are emitted
        mock_tc_listener = Mock()
        mock_sc_listener = Mock()
        core_manager.transition_completed.connect(mock_tc_listener)
        core_manager.state_changed.connect(mock_sc_listener)

        # Manually trigger the internal handler
        core_manager._on_transition_completed("walking")

        # Verify both signals were emitted
        mock_tc_listener.assert_called_once_with("walking")
        mock_sc_listener.assert_called_once_with("walking")

    def test_on_user_clicked(self, core_manager):
        """on_user_clicked can be called without error."""
        # Currently just logs, no errors expected
        core_manager.on_user_clicked()
