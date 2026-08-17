"""Tests for `ChatSettings` — the chat settings store extracted from
`ChatController` (backlog #5, stage 1).

Owns the user-configurable chat settings (server URL, model, endpoint,
API key, temperature, timeout, stop tokens) plus the file-backed system
prompt, and their persistence: scalars debounce-write to ConfigManager,
the system prompt writes straight to its prompt file.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from doro_app.core.chat.settings import ChatSettings
from doro_app.utils.config_defaults import (
    DEFAULT_CHAT_STOP_TOKENS,
    DEFAULT_CHAT_MAX_STOP_TOKENS,
)


@pytest.fixture
def tmp_prompt_file(tmp_path):
    prompt_file = tmp_path / "system_prompt.txt"
    prompt_file.write_text("You are Doro, a helpful assistant.")
    return prompt_file


def _make_config_manager():
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
    manager.chat.stop_tokens = list(DEFAULT_CHAT_STOP_TOKENS)
    manager.chat.max_stop_tokens = DEFAULT_CHAT_MAX_STOP_TOKENS
    manager.update_chat = Mock()
    manager.save = Mock()
    return manager


@pytest.fixture
def config_manager():
    return _make_config_manager()


@pytest.fixture
def settings(config_manager, tmp_prompt_file):
    return ChatSettings(config_manager=config_manager, prompt_path=tmp_prompt_file)


class TestInitialLoad:
    def test_loads_scalars_from_config_manager(self, settings):
        assert settings.server_url == "http://localhost:1234"
        assert settings.model == "mistral"
        assert settings.endpoint_path == "/v1/chat/completions"
        assert settings.timeout_seconds == 30
        assert settings.temperature == 0.7
        assert settings.api_key == ""

    def test_loads_system_prompt_from_file(self, settings):
        assert "Doro" in settings.system_prompt

    def test_stop_tokens_is_a_copy(self, settings, config_manager):
        # Mutating the returned list must not mutate internal state.
        tokens = settings.stop_tokens
        tokens.append("XXX")
        assert "XXX" not in settings.stop_tokens


class TestGetSetRoundTrip:
    def test_server_url_is_stripped(self, settings):
        settings.set_server_url("  http://new:5000  ")
        assert settings.server_url == "http://new:5000"

    def test_model_round_trips(self, settings):
        settings.set_model("llama-2")
        assert settings.model == "llama-2"

    def test_endpoint_path_round_trips(self, settings):
        settings.set_endpoint_path("/api/chat")
        assert settings.endpoint_path == "/api/chat"

    def test_temperature_coerced_to_float(self, settings):
        settings.set_temperature(1)
        assert settings.temperature == 1.0
        assert isinstance(settings.temperature, float)

    def test_timeout_coerced_to_int(self, settings):
        settings.set_timeout_seconds(60)
        assert settings.timeout_seconds == 60

    def test_api_key_is_stripped(self, settings):
        settings.set_api_key("  sk-abc  ")
        assert settings.api_key == "sk-abc"

    def test_max_stop_tokens_floored_at_zero(self, settings):
        settings.set_max_stop_tokens(-4)
        assert settings.max_stop_tokens == 0


class TestSystemPrompt:
    def test_update_writes_file_and_strips(self, settings, tmp_prompt_file):
        settings.update_system_prompt("  New prompt  ")
        assert settings.system_prompt == "New prompt"
        assert tmp_prompt_file.read_text() == "  New prompt  "  # file keeps raw text


class TestPersistence:
    def test_setter_schedules_debounced_persist(self, settings):
        with patch.object(settings._persist_timer, "start") as mock_start:
            settings.set_server_url("http://x:1")
            mock_start.assert_called_once()

    def test_persist_writes_to_config_manager(self, settings, config_manager):
        settings.set_server_url("http://test:8000")
        settings.set_model("test-model")

        settings._persist()  # trigger directly (bypass the debounce timer)

        config_manager.update_chat.assert_called()
        config_manager.save.assert_called()
        _, kwargs = config_manager.update_chat.call_args
        assert kwargs["server_url"] == "http://test:8000"
        assert kwargs["model"] == "test-model"

    def test_updating_system_prompt_does_not_touch_config_manager(
        self, settings, config_manager
    ):
        """System prompt is file-backed; it must not schedule a QSettings write."""
        with patch.object(settings._persist_timer, "start") as mock_start:
            settings.update_system_prompt("New")
            mock_start.assert_not_called()
