"""Tests for ConfigManager."""

import pytest
from pathlib import Path
from PySide6 import QtCore

from doro_app.utils.config_manager import ConfigManager
from doro_app.utils.config_schema import ChatConfig, UIConfig, AppConfig


class TestConfigManagerInitialization:
    """Tests for ConfigManager initialization."""

    def test_init_with_custom_path(self, tmp_path):
        """Can initialize with custom settings path."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        assert manager is not None
        assert manager.chat is not None
        assert manager.ui is not None
        assert manager.app is not None

    def test_init_with_defaults(self, tmp_path):
        """Initializes with default values when no settings exist."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        # Should have default chat config
        assert manager.chat.server_url == "http://127.0.0.1:1234"
        assert manager.chat.model == "lmstudio"
        assert manager.chat.timeout_seconds == 30
        assert manager.chat.temperature == 0.7

        # Should have default UI config
        assert manager.ui.bubble_offset_x == 120.0
        assert manager.ui.bubble_offset_y == -110.0
        assert manager.ui.bubble_scale == 1.0

        # Should have default app config
        assert manager.app.current_state == "idle"


class TestConfigManagerReadAccess:
    """Tests for reading configuration."""

    def test_chat_property_read_only(self, tmp_path):
        """Chat config property returns ChatConfig instance."""
        manager = ConfigManager(tmp_path / "test.ini")
        chat = manager.chat

        assert isinstance(chat, ChatConfig)
        assert chat.server_url == "http://127.0.0.1:1234"

    def test_ui_property_read_only(self, tmp_path):
        """UI config property returns UIConfig instance."""
        manager = ConfigManager(tmp_path / "test.ini")
        ui = manager.ui

        assert isinstance(ui, UIConfig)
        assert ui.bubble_scale == 1.0

    def test_app_property_read_only(self, tmp_path):
        """App config property returns AppConfig instance."""
        manager = ConfigManager(tmp_path / "test.ini")
        app = manager.app

        assert isinstance(app, AppConfig)
        assert app.current_state == "idle"


class TestConfigManagerUpdate:
    """Tests for updating configuration."""

    def test_update_chat_single_field(self, tmp_path):
        """Can update single chat config field."""
        manager = ConfigManager(tmp_path / "test.ini")

        manager.update_chat(temperature=0.9)

        assert manager.chat.temperature == 0.9
        # Other fields unchanged
        assert manager.chat.server_url == "http://127.0.0.1:1234"
        assert manager.chat.timeout_seconds == 30

    def test_update_chat_multiple_fields(self, tmp_path):
        """Can update multiple chat config fields."""
        manager = ConfigManager(tmp_path / "test.ini")

        manager.update_chat(
            temperature=0.9,
            timeout_seconds=60,
            model="gpt-4"
        )

        assert manager.chat.temperature == 0.9
        assert manager.chat.timeout_seconds == 60
        assert manager.chat.model == "gpt-4"

    def test_update_chat_validates(self, tmp_path):
        """Update validates values."""
        manager = ConfigManager(tmp_path / "test.ini")

        # Invalid temperature
        with pytest.raises(ValueError, match="temperature must be between"):
            manager.update_chat(temperature=3.0)

        # Invalid timeout
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            manager.update_chat(timeout_seconds=-1)

    def test_update_ui_single_field(self, tmp_path):
        """Can update single UI config field."""
        manager = ConfigManager(tmp_path / "test.ini")

        manager.update_ui(bubble_scale=1.5)

        assert manager.ui.bubble_scale == 1.5
        assert manager.ui.bubble_offset_x == 120.0  # Unchanged

    def test_update_ui_validates(self, tmp_path):
        """Update validates UI values."""
        manager = ConfigManager(tmp_path / "test.ini")

        with pytest.raises(ValueError, match="bubble_scale must be positive"):
            manager.update_ui(bubble_scale=0)

    def test_update_app_current_state(self, tmp_path):
        """Can update app current state."""
        manager = ConfigManager(tmp_path / "test.ini")

        manager.update_app(current_state="happy")

        assert manager.app.current_state == "happy"

    def test_update_app_validates(self, tmp_path):
        """Update validates app values."""
        manager = ConfigManager(tmp_path / "test.ini")

        with pytest.raises(ValueError, match="current_state must be non-empty"):
            manager.update_app(current_state="")


class TestConfigManagerPersistence:
    """Tests for load/save operations."""

    def test_save_persists_chat_config(self, tmp_path):
        """Save writes chat config to QSettings."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        manager.update_chat(temperature=0.9, timeout_seconds=60)
        manager.save()

        # Create new manager with same settings file
        manager2 = ConfigManager(settings_path)

        # Values should be loaded
        assert manager2.chat.temperature == 0.9
        assert manager2.chat.timeout_seconds == 60

    def test_save_persists_ui_config(self, tmp_path):
        """Save writes UI config to QSettings."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        manager.update_ui(bubble_scale=1.5, bubble_offset_x=50.0)
        manager.save()

        manager2 = ConfigManager(settings_path)

        assert manager2.ui.bubble_scale == 1.5
        assert manager2.ui.bubble_offset_x == 50.0

    def test_save_persists_app_config(self, tmp_path):
        """Save writes app config to QSettings."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        manager.update_app(current_state="happy")
        manager.save()

        manager2 = ConfigManager(settings_path)

        assert manager2.app.current_state == "happy"

    def test_load_handles_invalid_values(self, tmp_path):
        """Load gracefully handles invalid persisted values."""
        settings_path = tmp_path / "test.ini"

        # Manually write invalid values
        settings = QtCore.QSettings(str(settings_path), QtCore.QSettings.Format.IniFormat)
        settings.setValue("chat/temperature", "not_a_number")
        settings.setValue("ui/bubble_scale", "also_invalid")
        settings.sync()

        # Should not crash, should use defaults
        manager = ConfigManager(settings_path)

        assert manager.chat.temperature == 0.7  # Default
        assert manager.ui.bubble_scale == 1.0  # Default

    def test_load_with_partial_config(self, tmp_path):
        """Load works when only some values are persisted."""
        settings_path = tmp_path / "test.ini"

        # Write only some values
        settings = QtCore.QSettings(str(settings_path), QtCore.QSettings.Format.IniFormat)
        settings.setValue("chat/temperature", 0.9)
        # No other chat values
        settings.sync()

        manager = ConfigManager(settings_path)

        # Persisted value loaded
        assert manager.chat.temperature == 0.9

        # Other values are defaults
        assert manager.chat.timeout_seconds == 30
        assert manager.chat.server_url == "http://127.0.0.1:1234"


class TestConfigManagerReset:
    """Tests for reset functionality."""

    def test_reset_to_defaults(self, tmp_path):
        """Reset restores all defaults."""
        manager = ConfigManager(tmp_path / "test.ini")

        # Change some values
        manager.update_chat(temperature=0.9, timeout_seconds=60)
        manager.update_ui(bubble_scale=2.0)
        manager.update_app(current_state="happy")

        # Reset
        manager.reset_to_defaults()

        # All values should be defaults
        assert manager.chat.temperature == 0.7
        assert manager.chat.timeout_seconds == 30
        assert manager.ui.bubble_scale == 1.0
        assert manager.app.current_state == "idle"

    def test_reset_does_not_auto_save(self, tmp_path):
        """Reset does not automatically persist."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        manager.update_chat(temperature=0.9)
        manager.save()

        # Reset but don't save
        manager.reset_to_defaults()

        # Create new manager - should still have old value
        manager2 = ConfigManager(settings_path)
        assert manager2.chat.temperature == 0.9  # Not reset on disk


class TestConfigManagerRawAccess:
    """Tests for raw QSettings access (migration helper)."""

    def test_raw_settings_access(self, tmp_path):
        """Can access underlying QSettings for migration."""
        manager = ConfigManager(tmp_path / "test.ini")

        settings = manager.raw_settings

        assert isinstance(settings, QtCore.QSettings)

    def test_raw_settings_can_read_values(self, tmp_path):
        """Raw settings can read persisted values."""
        settings_path = tmp_path / "test.ini"
        manager = ConfigManager(settings_path)

        manager.update_chat(temperature=0.9)
        manager.save()

        # Access through raw settings
        raw_value = manager.raw_settings.value("chat/temperature")
        assert float(raw_value) == 0.9


class TestConfigManagerEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_multiple_updates_before_save(self, tmp_path):
        """Can make multiple updates before saving."""
        manager = ConfigManager(tmp_path / "test.ini")

        manager.update_chat(temperature=0.8)
        manager.update_chat(temperature=0.9)
        manager.update_chat(timeout_seconds=60)

        assert manager.chat.temperature == 0.9
        assert manager.chat.timeout_seconds == 60

    def test_repr(self, tmp_path):
        """Has readable repr."""
        manager = ConfigManager(tmp_path / "test.ini")
        repr_str = repr(manager)

        assert "ConfigManager" in repr_str
        assert "config=" in repr_str

    def test_concurrent_access(self, tmp_path):
        """Multiple managers can access same settings file."""
        settings_path = tmp_path / "test.ini"

        manager1 = ConfigManager(settings_path)
        manager1.update_chat(temperature=0.9)
        manager1.save()

        # Second manager should see updated value
        manager2 = ConfigManager(settings_path)
        assert manager2.chat.temperature == 0.9
