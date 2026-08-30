"""Tests for ChatOrchestrator - chat coordination layer."""

from unittest.mock import Mock
import pytest

from doro_app.core.chat.orchestrator import ChatOrchestrator


@pytest.fixture
def mock_controller():
    """Create mock ChatController."""
    controller = Mock()
    # Mock signals
    controller.request_started = Mock()
    controller.request_started.connect = Mock()
    controller.request_succeeded = Mock()
    controller.request_succeeded.connect = Mock()
    controller.request_failed = Mock()
    controller.request_failed.connect = Mock()

    # Mock properties and methods
    controller.is_inflight = False
    # Settings now live on a ChatSettings object the orchestrator exposes
    # directly (orchestrator.settings) rather than via pass-through methods.
    controller.settings = Mock()

    # Mock methods
    controller.start_request = Mock(return_value=(True, None))
    controller.clear_history = Mock()

    return controller


@pytest.fixture
def mock_movement_manager():
    """Create mock MovementManager."""
    manager = Mock()
    manager.queue_movement = Mock()
    return manager


@pytest.fixture
def mock_state_service():
    """Create mock StateService."""
    service = Mock()
    service.has_state = Mock(return_value=True)
    return service


@pytest.fixture
def orchestrator(mock_controller, mock_movement_manager, mock_state_service):
    """Create ChatOrchestrator with mocked dependencies."""
    return ChatOrchestrator(
        controller=mock_controller,
        movement=mock_movement_manager,
        state_service=mock_state_service,
    )


# ═══════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════


class TestChatOrchestratorInitialization:
    """Test ChatOrchestrator initialization."""

    def test_initialization_succeeds(self, orchestrator):
        """ChatOrchestrator can be initialized."""
        assert orchestrator is not None

    def test_connects_to_controller_signals(self, mock_controller, orchestrator):
        """ChatOrchestrator connects to controller signals."""
        mock_controller.request_started.connect.assert_called_once()
        mock_controller.request_succeeded.connect.assert_called_once()
        mock_controller.request_failed.connect.assert_called_once()


# ═══════════════════════════════════════════════════════════
# Message Sending Tests
# ═══════════════════════════════════════════════════════════


class TestSendMessage:
    """Test message sending functionality."""

    def test_send_message_starts_request(self, orchestrator, mock_controller):
        """send_message delegates to controller.start_request."""
        result = orchestrator.send_message("Hello")

        assert result is True
        mock_controller.start_request.assert_called_once_with("Hello", is_auto=False)

    def test_send_message_with_auto_flag(self, orchestrator, mock_controller):
        """send_message passes is_auto flag to controller."""
        result = orchestrator.send_message("Auto message", is_auto=True)

        assert result is True
        mock_controller.start_request.assert_called_once_with("Auto message", is_auto=True)

    def test_send_message_rejects_when_inflight(self, orchestrator, mock_controller):
        """send_message rejects when previous request is inflight."""
        mock_controller.is_inflight = True

        # Connect listener to notification signal
        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello")

        assert result is False
        mock_controller.start_request.assert_not_called()
        # Should emit notification (not silent)
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        assert call_args[0] == "info"  # severity
        assert "already replying" in call_args[2].lower()  # message

    def test_send_message_silent_no_notification_when_inflight(self, orchestrator, mock_controller):
        """send_message with silent=True doesn't emit notification when inflight."""
        mock_controller.is_inflight = True

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello", silent=True)

        assert result is False
        mock_listener.assert_not_called()  # No notification when silent

    def test_send_message_handles_start_failure(self, orchestrator, mock_controller):
        """send_message handles controller start failure."""
        mock_controller.start_request.return_value = (False, "Network error")

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello")

        assert result is False
        # Should emit notification with error
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        assert call_args[0] == "warning"  # severity
        assert "Network error" in call_args[2]  # message

    def test_send_message_silent_no_notification_on_failure(self, orchestrator, mock_controller):
        """send_message with silent=True doesn't emit notification on failure."""
        mock_controller.start_request.return_value = (False, "Error")

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello", silent=True)

        assert result is False
        mock_listener.assert_not_called()


# ═══════════════════════════════════════════════════════════
# Configuration API Tests
# ═══════════════════════════════════════════════════════════


class TestConfigurationAPI:
    """The 14 pass-through getters/setters were replaced by one `settings`
    accessor exposing the controller's ChatSettings directly (backlog #5)."""

    def test_settings_exposes_controller_settings(self, orchestrator, mock_controller):
        """orchestrator.settings returns the controller's settings object,
        so UI code reaches settings without a forwarding layer."""
        assert orchestrator.settings is mock_controller.settings

    def test_clear_history(self, orchestrator, mock_controller):
        """clear_history delegates to controller."""
        orchestrator.clear_history()
        mock_controller.clear_history.assert_called_once()


# ═══════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════


class TestProperties:
    """Test orchestrator properties."""

    def test_is_inflight_delegates_to_controller(self, orchestrator, mock_controller):
        """is_inflight property delegates to controller."""
        mock_controller.is_inflight = False
        assert orchestrator.is_inflight is False

        mock_controller.is_inflight = True
        assert orchestrator.is_inflight is True


# ═══════════════════════════════════════════════════════════
# Event Handler Tests
# ═══════════════════════════════════════════════════════════


class TestEventHandlers:
    """Test internal event handlers."""

    def test_on_request_started_emits_busy_cursor(self, orchestrator):
        """_on_request_started emits busy cursor signal."""
        mock_listener = Mock()
        orchestrator.busy_cursor_requested.connect(mock_listener)

        # Trigger handler directly
        orchestrator._on_request_started("Hello", False)

        mock_listener.assert_called_once_with(True)

    def test_on_request_succeeded_emits_bubble_text(self, orchestrator):
        """_on_request_succeeded emits bubble text signal."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler with simple response
        orchestrator._on_request_succeeded("Hello there!", False)

        # Should emit bubble text
        mock_listener.assert_called()
        call_args = mock_listener.call_args[0]
        assert "Hello there!" in call_args[0]

    def test_on_request_failed_emits_bubble_text(self, orchestrator):
        """_on_request_failed emits bubble text with fallback message."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler
        orchestrator._on_request_failed("Connection timeout", False)

        # Should emit bubble text (not notification)
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        # First arg is the text (should be fallback message, not the error)
        assert isinstance(call_args[0], str)
        assert len(call_args[0]) > 0  # Has some text
        # Second arg is kwargs dict
        assert isinstance(call_args[1], dict)
        assert call_args[1].get("auto_hide") is True

    def test_on_request_failed_auto_no_bubble(self, orchestrator):
        """_on_request_failed doesn't emit bubble text for auto requests."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler with was_auto=True
        orchestrator._on_request_failed("Error", was_auto=True)

        # Should not emit bubble text for auto requests
        mock_listener.assert_not_called()


class TestControlTagLeak:
    """Movement/control-only replies must never show raw tags in the bubble."""

    def test_movement_only_response_clears_bubble_without_tag(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[MOVE:dir=right]", False)

        clear_listener.assert_called_once()
        # The raw tag must never reach the bubble via any emit.
        for emitted in text_listener.call_args_list:
            assert "MOVE" not in emitted[0][0]
            assert "[" not in emitted[0][0]

    def test_lowercase_move_only_response_clears_bubble(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[move:left]", False)

        clear_listener.assert_called_once()
        text_listener.assert_not_called()

    def test_state_and_mouse_only_response_clears_bubble(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[STATE:walk_right][mouse:click]", False)

        clear_listener.assert_called_once()
        for emitted in text_listener.call_args_list:
            assert "[" not in emitted[0][0]

    def test_dialogue_with_trailing_move_tag_strips_tag(self, orchestrator):
        text_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)

        orchestrator._on_request_succeeded("早安！ [MOVE:dir=right]", False)

        text_listener.assert_called()
        emitted = text_listener.call_args[0][0]
        assert "早安" in emitted
        assert "[" not in emitted and "]" not in emitted


class TestMouseBracketDeferred:
    """Mouse brackets must be enqueued behind move brackets in the dispatcher
    queue, regardless of text order — otherwise a click written before a
    move bracket would fire immediately, bypassing the wait."""

    def _make_orch_with_dispatcher(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        """Wire a fresh orchestrator with mock action_dispatcher/automation
        so we can observe the order in which actions land on the queue."""
        dispatcher = Mock()
        dispatcher.dispatch = Mock()
        automation = Mock()
        schedule = Mock()
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            automation=automation,
            action_dispatcher=dispatcher,
            schedule=schedule,
        )
        return orch, dispatcher

    def test_click_after_move_keeps_order(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        orch, dispatcher = self._make_orch_with_dispatcher(
            mock_controller,
            mock_movement_manager,
            mock_state_service,
        )
        orch._on_request_succeeded(
            "好！[MOVE:to;x=200;y=100] [mouse:click]",
            False,
        )
        kinds = [c.args[0].kind for c in dispatcher.dispatch.call_args_list]
        assert kinds == ["movement", "click"]

    def test_click_before_move_in_text_still_dispatches_after_move(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        """The defence in depth: even when the LLM puts `[mouse:click]`
        textually before `[move:to;...]`, the orchestrator defers the click
        so the dispatcher receives the movement action first. Without this,
        the click would fire immediately (movement never starts because the
        action queue head is the click action)."""
        orch, dispatcher = self._make_orch_with_dispatcher(
            mock_controller,
            mock_movement_manager,
            mock_state_service,
        )
        orch._on_request_succeeded(
            "好！[mouse:click] [MOVE:to;x=200;y=100]",
            False,
        )
        kinds = [c.args[0].kind for c in dispatcher.dispatch.call_args_list]
        assert kinds == ["movement", "click"]


class TestSimulateResponse:
    """simulate_response injects text through the real reply pipeline."""

    def test_simulate_shows_cleaned_dialogue_and_returns_it(self, orchestrator):
        text_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)

        shown = orchestrator.simulate_response("早安！ [MOVE:dir=right]")

        assert "早安" in shown
        assert "[" not in shown
        text_listener.assert_called()
        assert "[" not in text_listener.call_args[0][0]

    def test_simulate_actions_only_clears_bubble_returns_empty(self, orchestrator):
        clear_listener = Mock()
        orchestrator.bubble_clear_requested.connect(clear_listener)

        shown = orchestrator.simulate_response("[MOVE:dir=right]")

        assert shown == ""
        clear_listener.assert_called_once()
