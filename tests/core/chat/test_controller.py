"""Tests for ChatController - chat settings and request handling."""

import json
from unittest.mock import Mock

import pytest
from PySide6 import QtCore

from doro_app.core.chat.controller import ChatController
from doro_app.utils.config_defaults import (
    DEFAULT_CHAT_MAX_STOP_TOKENS,
    DEFAULT_CHAT_STOP_TOKENS,
)


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
    manager.chat.api_key = ""
    manager.chat.max_tokens = 512
    manager.chat.stop_tokens = list(DEFAULT_CHAT_STOP_TOKENS)
    manager.chat.max_stop_tokens = DEFAULT_CHAT_MAX_STOP_TOKENS
    manager.chat.structured_mode = "auto"
    return manager


@pytest.fixture
def mock_state_service():
    """Create mock StateService."""
    service = Mock()
    service.has_state = Mock(return_value=True)
    service.visible_state_keys = Mock(return_value=["idle", "happy", "walking"])
    return service


@pytest.fixture
def controller_with_qsettings(tmp_prompt_file, mock_state_service, mock_config_manager):
    """Create ChatController with ConfigManager."""
    # Use default ConfigManager (same values as legacy defaults)
    default_manager = Mock()
    default_manager.chat = Mock()
    default_manager.chat.max_retries = 3
    default_manager.chat.history_turns = 5
    default_manager.chat.server_url = "http://127.0.0.1:1234"
    default_manager.chat.model = "lmstudio"
    default_manager.chat.endpoint_path = "/v1/chat/completions"
    default_manager.chat.timeout_seconds = 30
    default_manager.chat.temperature = 0.7
    default_manager.chat.api_key = ""
    default_manager.chat.max_tokens = 512
    default_manager.chat.stop_tokens = list(DEFAULT_CHAT_STOP_TOKENS)
    default_manager.chat.max_stop_tokens = DEFAULT_CHAT_MAX_STOP_TOKENS
    default_manager.chat.structured_mode = "auto"
    default_manager.update_chat = Mock()
    default_manager.save = Mock()

    return ChatController(
        prompt_path=tmp_prompt_file,
        state_service=mock_state_service,
        state_text_provider=lambda: "idle, happy",
        movement_hint_provider=lambda: "none",
        config_manager=default_manager,
    )


@pytest.fixture
def controller_with_config_manager(tmp_prompt_file, mock_state_service, mock_config_manager):
    """Create ChatController with ConfigManager (custom config)."""
    return ChatController(
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

    def test_initialization_with_default_config(self, controller_with_qsettings):
        """ChatController can be initialized with default configuration."""
        assert controller_with_qsettings is not None
        assert controller_with_qsettings.settings.server_url == "http://127.0.0.1:1234"  # Default
        assert controller_with_qsettings.settings.model == "lmstudio"  # Default

    def test_initialization_with_config_manager(
        self, controller_with_config_manager, mock_config_manager
    ):
        """ChatController can be initialized with ConfigManager."""
        assert controller_with_config_manager is not None
        # Should use ConfigManager values, not defaults
        assert controller_with_config_manager.settings.server_url == "http://localhost:1234"
        assert controller_with_config_manager.settings.model == "mistral"
        assert controller_with_config_manager.settings.temperature == 0.7

    def test_loads_system_prompt_from_file(self, controller_with_qsettings):
        """ChatController loads system prompt from file (via its settings)."""
        assert "Doro" in controller_with_qsettings.settings.system_prompt

    def test_initializes_empty_history(self, controller_with_qsettings):
        """ChatController initializes with empty history."""
        assert controller_with_qsettings.has_history is False

    def test_initializes_not_inflight(self, controller_with_qsettings):
        """ChatController initializes with no request inflight."""
        assert controller_with_qsettings.is_inflight is False


# Configuration getters/setters + persistence now live on ChatSettings —
# see tests/core/chat/test_settings.py. The controller only exposes them
# through its `.settings` object (checked in the init tests above).


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

    def test_successful_reply_is_stored_as_json_in_history(self, controller_with_qsettings):
        """History keeps the whole structured reply (ADR 0005)."""
        from doro_app.core.chat.chat_reply import chat_reply_model

        ctrl = controller_with_qsettings
        reply = chat_reply_model(["idle"]).model_validate({"state": "idle", "line": "嗨"})
        received = []
        ctrl.request_succeeded.connect(lambda r, _auto: received.append(r))
        ctrl._current_request_id = "r1"
        ctrl._inflight = True
        ctrl._last_user_message = "早安"

        ctrl._handle_worker_result("r1", (reply, None))

        assert received == [reply]
        assert ctrl._history[0] == {"role": "user", "content": "早安"}
        assert json.loads(ctrl._history[1]["content"])["line"] == "嗨"
        assert ctrl.is_inflight is False

    def test_unusable_reply_fails_the_request(self, controller_with_qsettings):
        ctrl = controller_with_qsettings
        failed = []
        ctrl.request_failed.connect(lambda msg, _auto: failed.append(msg))
        ctrl._current_request_id = "r1"
        ctrl._inflight = True

        ctrl._handle_worker_result("r1", (None, "回覆不合格式：找不到 JSON 物件"))

        assert failed == ["回覆不合格式：找不到 JSON 物件"]
        assert ctrl._history == []

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

    def _capture(self, monkeypatch, text='{"state":"idle","line":"嗨","move":null,"tool":null}'):
        from doro_app.core.llm import structured
        from doro_app.core.llm.transport import Completion

        structured.forget_detected_modes()
        payloads = []

        def request(url, payload, timeout, api_key):
            payloads.append(payload)
            return Completion(text, None, 200)

        monkeypatch.setattr(structured.transport, "request_completion", request)
        return payloads

    def test_request_sends_history_then_system_folded_user_message(
        self, controller_with_qsettings, monkeypatch
    ):
        payloads = self._capture(monkeypatch)
        ctrl = controller_with_qsettings
        ctrl._history = [{"role": "user", "content": "早"}, {"role": "assistant", "content": "{}"}]

        reply, error = ctrl._build_request("Hello")()

        assert error is None and reply.line == "嗨"
        messages = payloads[0]["messages"]
        assert messages[:2] == ctrl._history
        assert messages[2]["role"] == "user"
        assert messages[2]["content"].startswith("<<SYS>>") and "Hello" in messages[2]["content"]
        assert payloads[0]["model"] == ctrl.settings.model
        assert payloads[0]["temperature"] == ctrl.settings.temperature
        assert "stop" in payloads[0]
        schema = payloads[0]["response_format"]["json_schema"]["schema"]
        assert "tool" in schema["properties"]

    def test_web_answer_request_has_no_tool_field(self, controller_with_qsettings, monkeypatch):
        payloads = self._capture(monkeypatch)

        controller_with_qsettings._build_request("網頁內容…", web_answer=True)()

        schema = payloads[0]["response_format"]["json_schema"]["schema"]
        assert "tool" not in schema["properties"]
        assert "剛用瀏覽器讀完一個網頁" in payloads[0]["messages"][-1]["content"]

    def test_max_tokens_override_only_raises(self, controller_with_qsettings, monkeypatch):
        payloads = self._capture(monkeypatch)
        ctrl = controller_with_qsettings

        ctrl._build_request("Hi", max_tokens_override=1)()
        ctrl._build_request("Hi", max_tokens_override=5000)()

        assert payloads[0]["max_tokens"] == ctrl.settings.max_tokens
        assert payloads[1]["max_tokens"] == 5000

    def test_compose_system_prompt_includes_state_info(self, controller_with_qsettings):
        """_compose_system_prompt includes state information."""
        prompt = controller_with_qsettings._compose_system_prompt()

        # Should include the base system prompt
        assert "Doro" in prompt
        # Should include state information from provider
        assert "idle" in prompt or "happy" in prompt

    def test_compose_system_prompt_appends_doro_state(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """_compose_system_prompt appends the [Doro 當下狀態] block after movement hint."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "MOVE_HINT_MARKER",
            config_manager=mock_config_manager,
            doro_state_provider=lambda: "[Doro 當下狀態]\n位置: x=200, y=400\n螢幕: 1920×1080\n前景視窗 class: chrome",
        )

        prompt = controller._compose_system_prompt()

        assert "MOVE_HINT_MARKER" in prompt
        assert "[Doro 當下狀態]" in prompt
        assert "x=200, y=400" in prompt
        assert "1920×1080" in prompt
        assert "chrome" in prompt
        # Doro state must appear AFTER the movement hint, not before.
        assert prompt.index("MOVE_HINT_MARKER") < prompt.index("[Doro 當下狀態]")

    def test_compose_system_prompt_omits_doro_state_when_provider_empty(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """Empty doro_state_provider must not introduce blank trailing sections."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "MOVE_HINT_MARKER",
            config_manager=mock_config_manager,
            doro_state_provider=lambda: "",
        )

        prompt = controller._compose_system_prompt()

        assert "[Doro 當下狀態]" not in prompt
        # No trailing whitespace burp from the absent section.
        assert not prompt.endswith("\n\n\n")

    def test_compose_system_prompt_default_provider_is_noop(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """Omitting doro_state_provider behaves like the empty provider (back-compat)."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=mock_config_manager,
        )
        # No doro_state_provider passed — default lambda returns "".
        prompt = controller._compose_system_prompt()
        assert "[Doro 當下狀態]" not in prompt

    def test_compose_system_prompt_appends_a11y_tree_after_doro_state(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """The [前景視窗元件樹] block is injected after the [Doro 當下狀態] block."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "MOVE_HINT_MARKER",
            config_manager=mock_config_manager,
            doro_state_provider=lambda: "[Doro 當下狀態]\n位置: x=200, y=400",
            a11y_tree_provider=lambda: '[前景視窗元件樹]\nbutton "書籤" (1850,80 24x24)',
        )

        prompt = controller._compose_system_prompt()

        # 聊天規則本身也提到 [前景視窗元件樹]，所以比對注入區塊的開頭。
        assert "[前景視窗元件樹]\nbutton" in prompt
        assert "書籤" in prompt
        assert prompt.index("[Doro 當下狀態]") < prompt.index("[前景視窗元件樹]\nbutton")

    def test_compose_system_prompt_omits_a11y_tree_when_provider_empty(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """Empty a11y provider must not add a blank section or trailing burp."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=mock_config_manager,
            a11y_tree_provider=lambda: "",
        )
        prompt = controller._compose_system_prompt()
        assert "[前景視窗元件樹]" not in prompt.splitlines()
        assert not prompt.endswith("\n\n\n")

    def test_compose_system_prompt_a11y_default_provider_is_noop(
        self, tmp_prompt_file, mock_state_service, mock_config_manager
    ):
        """Omitting a11y_tree_provider behaves like the empty provider (back-compat)."""
        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=mock_config_manager,
        )
        prompt = controller._compose_system_prompt()
        assert "[前景視窗元件樹]" not in prompt.splitlines()


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


# Persistence (debounced ConfigManager writes) now lives on ChatSettings —
# see tests/core/chat/test_settings.py::TestPersistence.


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

    def test_config_manager_validates_values(self, tmp_prompt_file, mock_state_service):
        """ConfigManager validates configuration values."""
        # ConfigManager handles validation internally
        # Just verify controller uses ConfigManager values
        manager = Mock()
        manager.chat = Mock()
        manager.chat.max_retries = 5
        manager.chat.history_turns = 10
        manager.chat.server_url = "http://custom:9999"
        manager.chat.model = "custom-model"
        manager.chat.endpoint_path = "/custom/endpoint"
        manager.chat.timeout_seconds = 60
        manager.chat.temperature = 0.9
        manager.chat.api_key = ""
        manager.chat.stop_tokens = list(DEFAULT_CHAT_STOP_TOKENS)
        manager.chat.max_stop_tokens = DEFAULT_CHAT_MAX_STOP_TOKENS
        manager.update_chat = Mock()
        manager.save = Mock()

        controller = ChatController(
            prompt_path=tmp_prompt_file,
            state_service=mock_state_service,
            state_text_provider=lambda: "idle",
            movement_hint_provider=lambda: "none",
            config_manager=manager,
        )

        # Verify ConfigManager values are used
        assert controller.settings.timeout_seconds == 60
        assert controller.settings.temperature == 0.9
        assert controller.settings.server_url == "http://custom:9999"
