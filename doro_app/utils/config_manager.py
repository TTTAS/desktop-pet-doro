"""Centralized configuration management with type-safe access.

This module provides a unified interface for all application configuration,
replacing scattered QSettings access with a single, validated entry point.

Benefits over direct QSettings access:
- Type safety: config.chat.timeout_seconds (not "chat/timeout_seconds")
- Validation: Invalid values caught early with clear error messages
- Testability: Easy to mock and test configuration
- Maintainability: All config logic in one place
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6 import QtCore

from .config_schema import ChatConfig, UIConfig, AppConfig, DoroConfig
from ..constants import (
    CHAT_DEFAULT_HISTORY_TURNS,
    CHAT_DEFAULT_TIMEOUT_SECONDS,
    CHAT_DEFAULT_TEMPERATURE,
    CHAT_DEFAULT_MAX_TOKENS,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
)
from .config_defaults import (
    DEFAULT_CHAT_SERVER_URL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CHAT_ENDPOINT_PATH,
    DEFAULT_CHAT_API_KEY,
    DEFAULT_CHAT_MAX_RETRIES,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════
# Type Conversion Helpers
# ═══════════════════════════════════════════════════════════


def _safe_int(value: Any, default: int) -> int:
    """Convert value to int, return default if conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    """Convert value to float, return default if conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str) -> str:
    """Convert value to str, return default if empty or None."""
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


# ═══════════════════════════════════════════════════════════
# ConfigManager
# ═══════════════════════════════════════════════════════════


class ConfigManager:
    """
    Centralized, type-safe configuration management.

    Replaces scattered QSettings access with a single validated interface.
    All configuration is loaded at initialization and can be updated through
    type-safe methods.

    Example:
        # Create manager
        manager = ConfigManager(settings_path)

        # Type-safe access (IDE autocomplete works!)
        timeout = manager.chat.timeout_seconds
        temperature = manager.chat.temperature

        # Update with validation
        manager.update_chat(temperature=0.9)
        manager.save()

        # Compare to old way:
        timeout = _safe_int(settings.value("chat/timeout_seconds", 30), 30)
        settings.setValue("chat/temperature", 0.9)
        settings.sync()
    """

    def __init__(self, settings_path: Path | None = None):
        """
        Initialize configuration manager.

        Args:
            settings_path: Path to QSettings file. If None, uses default location.
        """
        # Lazy import to avoid requiring PySide6 at module load time
        from PySide6 import QtCore

        if settings_path:
            self._settings = QtCore.QSettings(
                str(settings_path),
                QtCore.QSettings.Format.IniFormat
            )
        else:
            # Use default QSettings location (platform-specific)
            self._settings = QtCore.QSettings("doro-pet", "doro")

        # Initialize config with defaults
        self._config = DoroConfig()

        # Load persisted config
        self.load()

        logger.info(f"ConfigManager initialized with settings at: {self._settings.fileName()}")

    # ═══════════════════════════════════════════════════════
    # Public API - Read-Only Access
    # ═══════════════════════════════════════════════════════

    @property
    def chat(self) -> ChatConfig:
        """Get chat configuration (read-only)."""
        return self._config.chat

    @property
    def ui(self) -> UIConfig:
        """Get UI configuration (read-only)."""
        return self._config.ui

    @property
    def app(self) -> AppConfig:
        """Get application configuration (read-only)."""
        return self._config.app

    @property
    def config(self) -> DoroConfig:
        """Get complete configuration (read-only)."""
        return self._config

    # ═══════════════════════════════════════════════════════
    # Public API - Updates
    # ═══════════════════════════════════════════════════════

    def update_chat(self, **kwargs) -> None:
        """
        Update chat configuration with validation.

        Args:
            **kwargs: Chat config fields to update (server_url, model, etc.)

        Raises:
            ValueError: If any value fails validation

        Example:
            manager.update_chat(temperature=0.9, timeout_seconds=60)
        """
        # Create new config with updated values
        current = self._config.chat
        updated_values = {
            "server_url": kwargs.get("server_url", current.server_url),
            "model": kwargs.get("model", current.model),
            "endpoint_path": kwargs.get("endpoint_path", current.endpoint_path),
            "api_key": kwargs.get("api_key", current.api_key),
            "timeout_seconds": kwargs.get("timeout_seconds", current.timeout_seconds),
            "temperature": kwargs.get("temperature", current.temperature),
            "max_tokens": kwargs.get("max_tokens", current.max_tokens),
            "max_retries": kwargs.get("max_retries", current.max_retries),
            "history_turns": kwargs.get("history_turns", current.history_turns),
        }

        # Validation happens in ChatConfig.__post_init__
        new_config = ChatConfig(**updated_values)
        self._config.chat = new_config

        logger.debug(f"Chat config updated: {kwargs}")

    def update_ui(self, **kwargs) -> None:
        """
        Update UI configuration with validation.

        Args:
            **kwargs: UI config fields to update (bubble_offset_x, etc.)

        Raises:
            ValueError: If any value fails validation

        Example:
            manager.update_ui(bubble_scale=1.5)
        """
        current = self._config.ui
        updated_values = {
            "bubble_offset_x": kwargs.get("bubble_offset_x", current.bubble_offset_x),
            "bubble_offset_y": kwargs.get("bubble_offset_y", current.bubble_offset_y),
            "bubble_scale": kwargs.get("bubble_scale", current.bubble_scale),
        }

        new_config = UIConfig(**updated_values)
        self._config.ui = new_config

        logger.debug(f"UI config updated: {kwargs}")

    def update_app(self, **kwargs) -> None:
        """
        Update app configuration with validation.

        Args:
            **kwargs: App config fields to update (current_state, etc.)

        Raises:
            ValueError: If any value fails validation

        Example:
            manager.update_app(current_state="happy")
        """
        current = self._config.app
        updated_values = {
            "current_state": kwargs.get("current_state", current.current_state),
        }

        new_config = AppConfig(**updated_values)
        self._config.app = new_config

        logger.debug(f"App config updated: {kwargs}")

    # ═══════════════════════════════════════════════════════
    # Public API - Persistence
    # ═══════════════════════════════════════════════════════

    def load(self) -> None:
        """
        Load configuration from QSettings.

        Validates all loaded values. If validation fails, logs warning and
        uses default value.
        """
        logger.debug("Loading configuration from QSettings")

        # Load chat config
        try:
            chat_config = ChatConfig(
                server_url=_safe_str(
                    self._settings.value("chat/server_url"),
                    DEFAULT_CHAT_SERVER_URL
                ),
                model=_safe_str(
                    self._settings.value("chat/model"),
                    DEFAULT_CHAT_MODEL
                ),
                endpoint_path=_safe_str(
                    self._settings.value("chat/endpoint_path"),
                    DEFAULT_CHAT_ENDPOINT_PATH
                ),
                api_key=_safe_str(
                    self._settings.value("chat/api_key"),
                    DEFAULT_CHAT_API_KEY
                ),
                timeout_seconds=_safe_int(
                    self._settings.value("chat/timeout_seconds"),
                    CHAT_DEFAULT_TIMEOUT_SECONDS
                ),
                temperature=_safe_float(
                    self._settings.value("chat/temperature"),
                    CHAT_DEFAULT_TEMPERATURE
                ),
                max_tokens=_safe_int(
                    self._settings.value("chat/max_tokens"),
                    CHAT_DEFAULT_MAX_TOKENS
                ),
                max_retries=_safe_int(
                    self._settings.value("chat/max_retries"),
                    DEFAULT_CHAT_MAX_RETRIES
                ),
                history_turns=_safe_int(
                    self._settings.value("chat/history_turns"),
                    CHAT_DEFAULT_HISTORY_TURNS
                ),
            )
            self._config.chat = chat_config
        except ValueError as e:
            logger.warning(f"Invalid chat config, using defaults: {e}")
            self._config.chat = ChatConfig()

        # Load UI config
        try:
            ui_config = UIConfig(
                bubble_offset_x=_safe_float(
                    self._settings.value("ui/bubble_offset_x"),
                    BUBBLE_DEFAULT_OFFSET_X
                ),
                bubble_offset_y=_safe_float(
                    self._settings.value("ui/bubble_offset_y"),
                    BUBBLE_DEFAULT_OFFSET_Y
                ),
                bubble_scale=_safe_float(
                    self._settings.value("ui/bubble_scale"),
                    BUBBLE_DEFAULT_SCALE
                ),
            )
            self._config.ui = ui_config
        except ValueError as e:
            logger.warning(f"Invalid UI config, using defaults: {e}")
            self._config.ui = UIConfig()

        # Load app config
        try:
            app_config = AppConfig(
                current_state=_safe_str(
                    self._settings.value("current_state"),
                    "idle"
                ),
            )
            self._config.app = app_config
        except ValueError as e:
            logger.warning(f"Invalid app config, using defaults: {e}")
            self._config.app = AppConfig()

        logger.info("Configuration loaded successfully")

    def save(self) -> None:
        """
        Save current configuration to QSettings.

        Persists all configuration sections to disk.
        """
        logger.debug("Saving configuration to QSettings")

        # Save chat config
        chat = self._config.chat
        self._settings.setValue("chat/server_url", chat.server_url)
        self._settings.setValue("chat/model", chat.model)
        self._settings.setValue("chat/endpoint_path", chat.endpoint_path)
        self._settings.setValue("chat/api_key", chat.api_key)
        self._settings.setValue("chat/timeout_seconds", chat.timeout_seconds)
        self._settings.setValue("chat/temperature", float(chat.temperature))
        self._settings.setValue("chat/max_tokens", chat.max_tokens)
        self._settings.setValue("chat/max_retries", chat.max_retries)
        self._settings.setValue("chat/history_turns", chat.history_turns)

        # Save UI config
        ui = self._config.ui
        self._settings.setValue("ui/bubble_offset_x", float(ui.bubble_offset_x))
        self._settings.setValue("ui/bubble_offset_y", float(ui.bubble_offset_y))
        self._settings.setValue("ui/bubble_scale", float(ui.bubble_scale))

        # Save app config
        app = self._config.app
        self._settings.setValue("current_state", app.current_state)

        # Ensure changes are written to disk
        self._settings.sync()

        logger.info("Configuration saved successfully")

    def reset_to_defaults(self) -> None:
        """
        Reset all configuration to default values.

        Does not save automatically - call save() to persist.
        """
        logger.info("Resetting configuration to defaults")
        self._config = DoroConfig()

    # ═══════════════════════════════════════════════════════
    # Public API - Raw QSettings Access (for migration)
    # ═══════════════════════════════════════════════════════

    @property
    def raw_settings(self) -> QtCore.QSettings:
        """
        Get underlying QSettings object.

        This is provided for gradual migration. New code should use
        ConfigManager methods instead of direct QSettings access.

        Deprecated: Will be removed after migration is complete.
        """
        return self._settings

    def __repr__(self) -> str:
        """Readable representation."""
        return f"ConfigManager(config={self._config})"
