"""Tests for configuration schema dataclasses."""

import pytest

from doro_app.utils.config_schema import ChatConfig, UIConfig, AppConfig, DoroConfig


class TestChatConfig:
    """Tests for ChatConfig validation."""

    def test_default_values(self):
        """Default values are set correctly."""
        config = ChatConfig()
        assert config.server_url == "http://127.0.0.1:1234"
        assert config.model == "lmstudio"
        assert config.endpoint_path == "/v1/chat/completions"
        assert config.timeout_seconds == 30
        assert config.temperature == 0.7
        assert config.max_tokens == 512
        assert config.max_retries == 2
        assert config.history_turns == 8

    def test_custom_values(self):
        """Can set custom values."""
        config = ChatConfig(
            server_url="http://localhost:8080",
            model="gpt-4",
            timeout_seconds=60,
            temperature=0.9,
        )
        assert config.server_url == "http://localhost:8080"
        assert config.model == "gpt-4"
        assert config.timeout_seconds == 60
        assert config.temperature == 0.9

    def test_validation_timeout(self):
        """Timeout must be positive integer."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            ChatConfig(timeout_seconds=0)

        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            ChatConfig(timeout_seconds=-1)

    def test_validation_temperature(self):
        """Temperature must be between 0.0 and 2.0."""
        with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
            ChatConfig(temperature=-0.1)

        with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
            ChatConfig(temperature=2.1)

    def test_validation_max_tokens(self):
        """Max tokens must be positive integer."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ChatConfig(max_tokens=0)

        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ChatConfig(max_tokens=-100)

    def test_validation_max_retries(self):
        """Max retries must be non-negative integer."""
        # 0 is valid (no retries)
        config = ChatConfig(max_retries=0)
        assert config.max_retries == 0

        # Negative is invalid
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            ChatConfig(max_retries=-1)

    def test_validation_history_turns(self):
        """History turns must be non-negative integer."""
        # 0 is valid (no history)
        config = ChatConfig(history_turns=0)
        assert config.history_turns == 0

        # Negative is invalid
        with pytest.raises(ValueError, match="history_turns must be non-negative"):
            ChatConfig(history_turns=-1)

    def test_config_key_prefix(self):
        """Config key prefix is 'chat'."""
        config = ChatConfig()
        assert config.config_key_prefix == "chat"


class TestUIConfig:
    """Tests for UIConfig validation."""

    def test_default_values(self):
        """Default values are set correctly."""
        config = UIConfig()
        assert config.bubble_offset_x == 120.0
        assert config.bubble_offset_y == -110.0
        assert config.bubble_scale == 1.0

    def test_custom_values(self):
        """Can set custom values."""
        config = UIConfig(
            bubble_offset_x=50.0,
            bubble_offset_y=-200.0,
            bubble_scale=1.5,
        )
        assert config.bubble_offset_x == 50.0
        assert config.bubble_offset_y == -200.0
        assert config.bubble_scale == 1.5

    def test_validation_bubble_scale(self):
        """Bubble scale must be positive."""
        with pytest.raises(ValueError, match="bubble_scale must be positive"):
            UIConfig(bubble_scale=0)

        with pytest.raises(ValueError, match="bubble_scale must be positive"):
            UIConfig(bubble_scale=-1.0)

    def test_negative_offsets_allowed(self):
        """Negative offsets are valid."""
        config = UIConfig(bubble_offset_x=-50.0, bubble_offset_y=-100.0)
        assert config.bubble_offset_x == -50.0
        assert config.bubble_offset_y == -100.0

    def test_config_key_prefix(self):
        """Config key prefix is 'ui'."""
        config = UIConfig()
        assert config.config_key_prefix == "ui"


class TestAppConfig:
    """Tests for AppConfig validation."""

    def test_default_values(self):
        """Default values are set correctly."""
        config = AppConfig()
        assert config.current_state == "idle"

    def test_custom_values(self):
        """Can set custom values."""
        config = AppConfig(current_state="happy")
        assert config.current_state == "happy"

    def test_validation_empty_state(self):
        """Current state cannot be empty."""
        with pytest.raises(ValueError, match="current_state must be non-empty"):
            AppConfig(current_state="")

        with pytest.raises(ValueError, match="current_state must be non-empty"):
            AppConfig(current_state="   ")

    def test_whitespace_normalization(self):
        """Whitespace is trimmed from state names."""
        config = AppConfig(current_state="  happy  ")
        assert config.current_state == "happy"

    def test_config_key_prefix(self):
        """Config key prefix is empty (root level)."""
        config = AppConfig()
        assert config.config_key_prefix == ""


class TestDoroConfig:
    """Tests for combined DoroConfig."""

    def test_default_construction(self):
        """Can create with all defaults."""
        config = DoroConfig()
        assert config.chat.server_url == "http://127.0.0.1:1234"
        assert config.ui.bubble_scale == 1.0
        assert config.app.current_state == "idle"

    def test_partial_construction(self):
        """Can create with partial config."""
        config = DoroConfig(
            chat=ChatConfig(temperature=0.5),
            ui=UIConfig(bubble_scale=2.0),
        )
        assert config.chat.temperature == 0.5
        assert config.chat.server_url == "http://127.0.0.1:1234"  # Still default
        assert config.ui.bubble_scale == 2.0
        assert config.app.current_state == "idle"

    def test_repr(self):
        """Repr is readable and informative."""
        config = DoroConfig()
        repr_str = repr(config)
        assert "DoroConfig" in repr_str
        assert "ChatConfig" in repr_str
        assert "UIConfig" in repr_str
        assert "AppConfig" in repr_str
        assert "lmstudio" in repr_str
        assert "idle" in repr_str
