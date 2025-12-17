"""Tests for ChatController - chat settings and request handling."""

from unittest.mock import Mock, MagicMock, patch, call
import pytest
from pathlib import Path
from PySide6 import QtCore

from doro_app.core.chat.controller import ChatController


@pytest.fixture
def tmp_prompt_file(tmp_path):
    """Create a temporary prompt file."""
    prompt_file = tmp_path / "system_prompt.txt"
    prompt_file.write_text("You are Doro, a helpful assistant.")
    return prompt_file


@pytest.fixture
def mock_qsettings(tmp_path):
    """Create mock QSettings."""
    config = QtCore.QSettings(str(tmp_path / "test.ini"), QtCore.QSettings.Format.IniFormat)
    return config


@pytest.fixture
def mock_config_manager():
    """Create mock ConfigManager."""
    manager = Mock()
    manager.chat = Mock()
    manager.chat.max_retries = 3
    manager.chat.history_turns = 5
    manager.chat.server_url = "http://localhost:1234"
    manager.chat.model = "mistral"
    manager.chat.endpoint_path = "/v1/chat/completions"
    manager.chat.timeout_seconds = 30
    manager.chat.temperature = 0.7
    return manager


@pytest.fixture
def mock_state_service():
    """Create mock StateService."""
    service = Mock()
    service.has_state = Mock(return_value=True)
    service.visible_state_keys = Mock(return_value=["idle", "happy", "walking"])
    return service


@pytest.fixture
def controller_with_qsettings(mock_qsettings, tmp_prompt_file, mock_state_service):
    """Create ChatController with QSettings (legacy mode)."""
    return ChatController(
        config=mock_qsettings,
        prompt_path=tmp_prompt_file,
        state_service=mock_state_service,
        state_text_provider=lambda: "idle, happy",
        movement_hint_provider=lambda: "none",
        config_manager=None,  # Force legacy mode
    )


@pytest.fixture
def controller_with_config_manager(mock_qsettings, tmp_prompt_file, mock_state_service, mock_config_manager):
    """Create ChatController with ConfigManager (new mode)."""
    return ChatController(
        config=mock_qsettings,
        prompt_path=tmp_prompt_file,
        state_service=mock_state_service,
        state_text_provider=lambda: "idle, happy",
        movement_hint_provider=lambda: "none",
        config_manager=mock_config_manager,
    )


# ═══════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════


class TestChatControllerInitialization:
    """Test ChatController initialization."""

    def test_initialization_with_qsettings(self, controller_with_qsettings):
        """ChatController can be initialized with QSettings."""
        assert controller_with_qsettings is not None
        assert controller_with_qsettings.server_url == "http://127.0.0.1:1234"  # Default
        assert controller_with_qsettings.model == "lmstudio"  # Default

    def test_initialization_with_config_manager(self, controller_with_config_manager, mock_config_manager):
        """ChatController can be initialized with ConfigManager."""
        assert controller_with_config_manager is not None
        # Should use ConfigManager values, not defaults
        assert controller_with_config_manager.server_url == "http://localhost:1234"
        assert controller_with_config_manager.model == "mistral"
        assert controller_with_config_manager.temperature == 0.7

    def test_loads_system_prompt_from_file(self, controller_with_qsettings):
        """ChatController loads system prompt from file."""
        assert "Doro" in controller_with_qsettings.system_prompt

    def test_initializes_empty_history(self, controller_with_qsettings):
        """ChatController initializes with empty history."""
        assert controller_with_qsettings.has_history is False

    def test_initializes_not_inflight(self, controller_with_qsettings):
        """ChatController initializes with no request inflight."""
        assert controller_with_qsettings.is_inflight is False


# ═══════════════════════════════════════════════════════════
# Configuration Property Tests
# ═══════════════════════════════════════════════════════════


class TestConfigurationProperties:
    """Test configuration getters and setters."""

    def test_get_system_prompt(self, controller_with_qsettings):
        """system_prompt property returns loaded prompt."""
        prompt = controller_with_qsettings.system_prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_update_system_prompt(self, controller_with_qsettings, tmp_prompt_file):
        """update_system_prompt updates prompt and saves to file."""
        controller_with_qsettings.update_system_prompt("New prompt")
        assert controller_with_qsettings.system_prompt == "New prompt"
        # Verify file was updated
        assert tmp_prompt_file.read_text() == "New prompt"

    def test_get_set_server_url(self, controller_with_qsettings):
        """server_url can be get and set."""
        controller_with_qsettings.set_server_url("http://new-server:5000")
        assert controller_with_qsettings.server_url == "http://new-server:5000"

    def test_get_set_model(self, controller_with_qsettings):
        """model can be get and set."""
        controller_with_qsettings.set_model("llama-2")
        assert controller_with_qsettings.model == "llama-2"

    def test_get_set_endpoint_path(self, controller_with_qsettings):
        """endpoint_path can be get and set."""
        controller_with_qsettings.set_endpoint_path("/api/chat")
        assert controller_with_qsettings.endpoint_path == "/api/chat"

    def test_get_set_temperature(self, controller_with_qsettings):
        """temperature can be get and set."""
        controller_with_qsettings.set_temperature(0.9)
        assert controller_with_qsettings.temperature == 0.9

    def test_get_set_timeout_seconds(self, controller_with_qsettings):
        """timeout_seconds can be get and set."""
        controller_with_qsettings.set_timeout_seconds(60)
        assert controller_with_qsettings.timeout_seconds == 60


# ═══════════════════════════════════════════════════════════
# History Management Tests
# ═══════════════════════════════════════════════════════════


class TestHistoryManagement:
    """Test chat history management."""

    def test_has_history_false_when_empty(self, controller_with_qsettings):
        """has_history returns False when history is empty."""
        assert controller_with_qsettings.has_history is False

    def test_clear_history(self, controller_with_qsettings):
        """clear_history removes all history."""
        # Add some history manually
        controller_with_qsettings._history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        assert controller_with_qsettings.has_history is True

        controller_with_qsettings.clear_history()
        assert controller_with_qsettings.has_history is False


# ═══════════════════════════════════════════════════════════
# Request Lifecycle Tests
# ═══════════════════════════════════════════════════════════


class TestRequestLifecycle:
    """Test chat request lifecycle."""

    def test_start_request_rejects_when_inflight(self, controller_with_qsettings):
        """start_request rejects when request is already inflight."""
        # Set inflight state manually
        controller_with_qsettings._inflight = True

        success, error = controller_with_qsettings.start_request("Hello")

        assert success is False
        assert "already" in error.lower()

    def test_build_payload_called_with_message(self, controller_with_qsettings):
        """start_request uses the provided message for payload building."""
        # Test the payload building function directly
        payload = controller_with_qsettings._build_chat_payload("Test message")

        # Verify the message is in the payload
        assert "messages" in payload
        # Should contain the test message somewhere
        messages_str = str(payload["messages"])
        assert "Test message" in messages_str

    def test_cancel_inflight_sets_cancelled_state(self, controller_with_qsettings):
        """cancel_inflight marks request as cancelled."""
        # Set up inflight state
        controller_with_qsettings._inflight = True
        controller_with_qsettings._current_request_id = "test-request-123"

        controller_with_qsettings.cancel_inflight()

        assert "test-request-123" in controller_with_qsettings._cancelled_requests

    def test_is_inflight_property(self, controller_with_qsettings):
        """is_inflight property reflects internal state."""
        assert controller_with_qsettings.is_inflight is False

        controller_with_qsettings._inflight = True
        assert controller_with_qsettings.is_inflight is True


# ═══════════════════════════════════════════════════════════
# Payload Building Tests
# ═══════════════════════════════════════════════════════════


class TestPayloadBuilding:
    """Test chat payload construction."""

    def test_build_chat_payload_includes_user_message(self, controller_with_qsettings):
        """_build_chat_payload includes user message."""
        payload = controller_with_qsettings._build_chat_payload("Hello")

        assert "messages" in payload
        # Should have at least the user message
        assert len(payload["messages"]) >= 1
        # User message should be in the messages
        user_messages = [m for m in payload["messages"] if m.get("role") == "user"]
        assert any("Hello" in m.get("content", "") for m in user_messages)

    def test_build_chat_payload_includes_config(self, controller_with_qsettings):
        """_build_chat_payload includes configuration."""
        payload = controller_with_qsettings._build_chat_payload("Hello")

        assert "model" in payload
        assert "temperature" in payload
        assert "max_tokens" in payload
        assert payload["model"] == controller_with_qsettings.model
        assert payload["temperature"] == controller_with_qsettings.temperature

    def test_compose_system_prompt_includes_state_info(self, controller_with_qsettings):
        """_compose_system_prompt includes state information."""
        prompt = controller_with_qsettings._compose_system_prompt()

        # Should include the base system prompt
        assert "Doro" in prompt
        # Should include state information from provider
        assert "idle" in prompt or "happy" in prompt


# ═══════════════════════════════════════════════════════════
# Signal Emission Tests
# ═══════════════════════════════════════════════════════════


class TestSignalEmission:
    """Test signal emissions."""

    def test_request_started_signal_can_be_connected(self, controller_with_qsettings):
        """request_started signal can be connected to."""
        mock_listener = Mock()
        # Just verify we can connect to the signal
        controller_with_qsettings.request_started.connect(mock_listener)
        # Signal connection successful (no exception)
        assert True


# ═══════════════════════════════════════════════════════════
# Configuration Persistence Tests
# ═══════════════════════════════════════════════════════════


class TestConfigurationPersistence:
    """Test configuration persistence to QSettings."""

    def test_set_server_url_schedules_persist(self, controller_with_qsettings):
        """Setting server_url schedules persistence."""
        # Mock the persist timer
        with patch.object(controller_with_qsettings._persist_timer, 'start') as mock_start:
            controller_with_qsettings.set_server_url("http://new-server:5000")
            mock_start.assert_called_once()

    def test_set_model_schedules_persist(self, controller_with_qsettings):
        """Setting model schedules persistence."""
        with patch.object(controller_with_qsettings._persist_timer, 'start') as mock_start:
            controller_with_qsettings.set_model("new-model")
            mock_start.assert_called_once()

    def test_persist_chat_settings_saves_to_qsettings(self, controller_with_qsettings, mock_qsettings):
        """_persist_chat_settings saves configuration to QSettings."""
        controller_with_qsettings.set_server_url("http://test:8000")
        controller_with_qsettings.set_model("test-model")

        # Trigger persist directly
        controller_with_qsettings._persist_chat_settings()

        # Verify values were saved
        assert mock_qsettings.value("chat/server_url") == "http://test:8000"
        assert mock_qsettings.value("chat/model") == "test-model"


# ═══════════════════════════════════════════════════════════
# Provider Callback Tests
# ═══════════════════════════════════════════════════════════


class TestProviderCallbacks:
    """Test state and movement provider callbacks."""

    def test_safe_call_provider_handles_errors(self, controller_with_qsettings):
        """_safe_call_provider handles provider exceptions gracefully."""
        def failing_provider():
            raise Exception("Provider failed")

        result = controller_with_qsettings._safe_call_provider(failing_provider)

        # Should return empty string on error, not crash
        assert result == ""

    def test_safe_call_provider_returns_value(self, controller_with_qsettings):
        """_safe_call_provider returns provider value."""
        def working_provider():
            return "test value"

        result = controller_with_qsettings._safe_call_provider(working_provider)

        assert result == "test value"


# ═══════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_timeout_value_uses_default(self, mock_qsettings, tmp_prompt_file, mock_state_service):
        """Invalid timeout value in QSettings uses default."""
        # Set invalid timeout
        mock_qsettings.setValue("chat/timeout_seconds", "invalid")

        controller = ChatController(
            config=mock_qsettings,
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=None,
        )

        # Should use default value
        assert controller.timeout_seconds == 30  # DEFAULT

    def test_invalid_temperature_value_uses_default(self, mock_qsettings, tmp_prompt_file, mock_state_service):
        """Invalid temperature value in QSettings uses default."""
        # Set invalid temperature
        mock_qsettings.setValue("chat/temperature", "not-a-number")

        controller = ChatController(
            config=mock_qsettings,
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=None,
        )

        # Should use default value
        assert controller.temperature == 0.7  # DEFAULT
