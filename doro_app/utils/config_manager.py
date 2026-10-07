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

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore

from ..constants import (
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
    CHAT_DEFAULT_HISTORY_TURNS,
    CHAT_DEFAULT_MAX_TOKENS,
    CHAT_DEFAULT_TEMPERATURE,
    CHAT_DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_A11Y_APP_BLACKLIST,
    DEFAULT_MOUSE_TARGET_ALLOWLIST,
)
from ..utils.logger import get_logger
from .config_defaults import (
    DEFAULT_A11Y_ENABLED,
    DEFAULT_A11Y_SHARE_INPUT_VALUES,
    DEFAULT_CHAT_API_KEY,
    DEFAULT_CHAT_ENDPOINT_PATH,
    DEFAULT_CHAT_MAX_RETRIES,
    DEFAULT_CHAT_MAX_STOP_TOKENS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CHAT_SERVER_URL,
    DEFAULT_CHAT_STOP_TOKENS,
    DEFAULT_CHAT_STRUCTURED_MODE,
    DEFAULT_MOUSE_AUTOMATION_ENABLED,
    DEFAULT_TAVILY_API_KEY,
    DEFAULT_VERIFY_SEARCH_DEPTH,
    DEFAULT_WEB_OPERATION_ENABLED,
)
from .config_schema import AppConfig, AutomationConfig, ChatConfig, DoroConfig, UIConfig, WebConfig

logger = get_logger(__name__)


def _companion_poses(value: Any) -> list[str]:
    try:
        parsed = json.loads(value) if value is not None else ["happy"]
        if isinstance(parsed, list):
            return list(dict.fromkeys(k for k in parsed if isinstance(k, str) and k.strip()))
    except (TypeError, ValueError):
        pass
    return ["happy"]


def _foot_overrides(value: Any) -> dict[str, float]:
    try:
        parsed = json.loads(value or "{}")
        if not isinstance(parsed, dict):
            return {}
        return {
            k: v
            for k, v in parsed.items()
            if isinstance(k, str)
            and k
            and isinstance(v, (int, float))
            and not isinstance(v, bool)
            and 0 <= v <= 1
        }
    except (TypeError, ValueError):
        return {}


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


def _safe_str_list(value: Any, default: list[str]) -> list[str]:
    """Convert value to list[str], return default if invalid."""
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(v) for v in value]
    return list(default)


def _safe_bool(value: Any, default: bool) -> bool:
    """Convert QSettings value to bool — QSettings returns strings like 'true'."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _parse_class_list(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a window-class list from QSettings (list/tuple or comma string)."""
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return default


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
            self._settings = QtCore.QSettings(str(settings_path), QtCore.QSettings.Format.IniFormat)
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
    def automation(self) -> AutomationConfig:
        """Get automation (synthetic mouse click) configuration (read-only)."""
        return self._config.automation

    @property
    def web(self) -> WebConfig:
        """Get web (search/verify) configuration (read-only)."""
        return self._config.web

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
            "stop_tokens": kwargs.get("stop_tokens", current.stop_tokens),
            "max_stop_tokens": kwargs.get("max_stop_tokens", current.max_stop_tokens),
            "structured_mode": kwargs.get("structured_mode", current.structured_mode),
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
            "quiet_companion": kwargs.get("quiet_companion", current.quiet_companion),
            "companion_home_x": kwargs.get("companion_home_x", current.companion_home_x),
            "companion_home_y": kwargs.get("companion_home_y", current.companion_home_y),
            "companion_interval_seconds": kwargs.get(
                "companion_interval_seconds", current.companion_interval_seconds
            ),
            "companion_effects": kwargs.get("companion_effects", current.companion_effects),
            "sprite_foot_overrides": kwargs.get(
                "sprite_foot_overrides", current.sprite_foot_overrides
            ),
            "companion_pose_keys": kwargs.get("companion_pose_keys", current.companion_pose_keys),
            "companion_rest_state": kwargs.get(
                "companion_rest_state", current.companion_rest_state
            ),
        }

        new_config = UIConfig(**updated_values)
        self._config.ui = new_config

        logger.debug(f"UI config updated: {kwargs}")

    def update_automation(self, **kwargs) -> None:
        """Update automation configuration with validation.

        Args:
            **kwargs: Fields to update — `mouse_enabled` (bool),
                `mouse_target_allowlist` (tuple[str, ...]).

        Raises:
            ValueError: If any value fails validation.
        """
        current = self._config.automation
        updated_values = {
            "mouse_enabled": kwargs.get("mouse_enabled", current.mouse_enabled),
            "mouse_target_allowlist": kwargs.get(
                "mouse_target_allowlist", current.mouse_target_allowlist
            ),
            "a11y_enabled": kwargs.get("a11y_enabled", current.a11y_enabled),
            "a11y_app_blacklist": kwargs.get("a11y_app_blacklist", current.a11y_app_blacklist),
            "a11y_share_input_values": kwargs.get(
                "a11y_share_input_values", current.a11y_share_input_values
            ),
            "web_operation_enabled": kwargs.get(
                "web_operation_enabled", current.web_operation_enabled
            ),
        }
        new_config = AutomationConfig(**updated_values)
        self._config.automation = new_config
        logger.debug(f"Automation config updated: {kwargs}")

    def update_web(self, **kwargs) -> None:
        """Update web (search/verify) configuration with validation."""
        current = self._config.web
        updated_values = {
            "tavily_api_key": kwargs.get("tavily_api_key", current.tavily_api_key),
            "verify_search_depth": kwargs.get("verify_search_depth", current.verify_search_depth),
        }
        self._config.web = WebConfig(**updated_values)
        logger.debug(f"Web config updated: {kwargs}")

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
                    self._settings.value("chat/server_url"), DEFAULT_CHAT_SERVER_URL
                ),
                model=_safe_str(self._settings.value("chat/model"), DEFAULT_CHAT_MODEL),
                endpoint_path=_safe_str(
                    self._settings.value("chat/endpoint_path"), DEFAULT_CHAT_ENDPOINT_PATH
                ),
                api_key=_safe_str(self._settings.value("chat/api_key"), DEFAULT_CHAT_API_KEY),
                timeout_seconds=_safe_int(
                    self._settings.value("chat/timeout_seconds"), CHAT_DEFAULT_TIMEOUT_SECONDS
                ),
                temperature=_safe_float(
                    self._settings.value("chat/temperature"), CHAT_DEFAULT_TEMPERATURE
                ),
                max_tokens=_safe_int(
                    self._settings.value("chat/max_tokens"), CHAT_DEFAULT_MAX_TOKENS
                ),
                max_retries=_safe_int(
                    self._settings.value("chat/max_retries"), DEFAULT_CHAT_MAX_RETRIES
                ),
                history_turns=_safe_int(
                    self._settings.value("chat/history_turns"), CHAT_DEFAULT_HISTORY_TURNS
                ),
                stop_tokens=_safe_str_list(
                    self._settings.value("chat/stop_tokens"), DEFAULT_CHAT_STOP_TOKENS
                ),
                max_stop_tokens=_safe_int(
                    self._settings.value("chat/max_stop_tokens"), DEFAULT_CHAT_MAX_STOP_TOKENS
                ),
                structured_mode=_safe_str(
                    self._settings.value("chat/structured_mode"), DEFAULT_CHAT_STRUCTURED_MODE
                ),
            )
            self._config.chat = chat_config
        except ValueError as e:
            logger.warning(f"Invalid chat config, using defaults: {e}")
            self._config.chat = ChatConfig()

        # Load UI config
        try:
            home_y = _safe_float(self._settings.value("ui/companion_home_y"), -1.0)
            legacy_activity = _safe_str(self._settings.value("ui/companion_activity"), "lively")
            interval = self._settings.value(
                "ui/companion_interval_seconds",
                {"lively": 9, "balanced": 60, "calm": 120}.get(legacy_activity, 9),
            )
            # QSettings may return integer strings; reject fractions and booleans.
            if isinstance(interval, str) and interval.isascii() and interval.isdecimal():
                interval = int(interval)
            if type(interval) is not int or not 1 <= interval <= 3600:
                interval = 9
            ui_config = UIConfig(
                bubble_offset_x=_safe_float(
                    self._settings.value("ui/bubble_offset_x"), BUBBLE_DEFAULT_OFFSET_X
                ),
                bubble_offset_y=_safe_float(
                    self._settings.value("ui/bubble_offset_y"), BUBBLE_DEFAULT_OFFSET_Y
                ),
                bubble_scale=_safe_float(
                    self._settings.value("ui/bubble_scale"), BUBBLE_DEFAULT_SCALE
                ),
                quiet_companion=_safe_bool(self._settings.value("ui/quiet_companion"), False),
                companion_home_x=_safe_float(self._settings.value("ui/companion_home_x"), 0.9),
                companion_home_y=home_y if 0 <= home_y <= 1 else None,
                companion_interval_seconds=interval,
                companion_effects=_safe_bool(self._settings.value("ui/companion_effects"), True),
                sprite_foot_overrides=_foot_overrides(
                    self._settings.value("ui/sprite_foot_overrides")
                ),
                companion_pose_keys=_companion_poses(
                    self._settings.value("ui/companion_pose_keys")
                ),
                companion_rest_state=_safe_str(
                    self._settings.value("ui/companion_rest_state"), "idle"
                ),
            )
            self._config.ui = ui_config
        except ValueError as e:
            logger.warning(f"Invalid UI config, using defaults: {e}")
            self._config.ui = UIConfig()

        # Load automation config
        try:
            allowlist = _parse_class_list(
                self._settings.value("automation/mouse_target_allowlist"),
                DEFAULT_MOUSE_TARGET_ALLOWLIST,
            )
            blacklist = _parse_class_list(
                self._settings.value("automation/a11y_app_blacklist"),
                DEFAULT_A11Y_APP_BLACKLIST,
            )

            automation_config = AutomationConfig(
                mouse_enabled=_safe_bool(
                    self._settings.value("automation/mouse_enabled"),
                    DEFAULT_MOUSE_AUTOMATION_ENABLED,
                ),
                mouse_target_allowlist=allowlist,
                a11y_enabled=_safe_bool(
                    self._settings.value("automation/a11y_enabled"),
                    DEFAULT_A11Y_ENABLED,
                ),
                a11y_app_blacklist=blacklist,
                a11y_share_input_values=_safe_bool(
                    self._settings.value("automation/a11y_share_input_values"),
                    DEFAULT_A11Y_SHARE_INPUT_VALUES,
                ),
                web_operation_enabled=_safe_bool(
                    self._settings.value("automation/web_operation_enabled"),
                    DEFAULT_WEB_OPERATION_ENABLED,
                ),
            )
            self._config.automation = automation_config
        except ValueError as e:
            logger.warning(f"Invalid automation config, using defaults: {e}")
            self._config.automation = AutomationConfig(
                mouse_enabled=DEFAULT_MOUSE_AUTOMATION_ENABLED,
                a11y_enabled=DEFAULT_A11Y_ENABLED,
                a11y_share_input_values=DEFAULT_A11Y_SHARE_INPUT_VALUES,
            )

        # Load web config
        try:
            web_config = WebConfig(
                tavily_api_key=_safe_str(
                    self._settings.value("web/tavily_api_key"),
                    DEFAULT_TAVILY_API_KEY,
                ),
                verify_search_depth=_safe_str(
                    self._settings.value("web/verify_search_depth"),
                    DEFAULT_VERIFY_SEARCH_DEPTH,
                ),
            )
            self._config.web = web_config
        except ValueError as e:
            logger.warning(f"Invalid web config, using defaults: {e}")
            self._config.web = WebConfig()

        # Load app config
        try:
            app_config = AppConfig(
                current_state=_safe_str(self._settings.value("current_state"), "idle"),
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
        self._settings.setValue("chat/stop_tokens", chat.stop_tokens)
        self._settings.setValue("chat/max_stop_tokens", chat.max_stop_tokens)
        self._settings.setValue("chat/structured_mode", chat.structured_mode)

        # Save UI config
        ui = self._config.ui
        self._settings.setValue("ui/bubble_offset_x", float(ui.bubble_offset_x))
        self._settings.setValue("ui/bubble_offset_y", float(ui.bubble_offset_y))
        self._settings.setValue("ui/bubble_scale", float(ui.bubble_scale))
        self._settings.setValue("ui/quiet_companion", ui.quiet_companion)
        self._settings.setValue("ui/companion_home_x", ui.companion_home_x)
        if ui.companion_home_y is None:
            self._settings.remove("ui/companion_home_y")
        else:
            self._settings.setValue("ui/companion_home_y", ui.companion_home_y)
        self._settings.remove("ui/companion_floor_interaction")
        self._settings.setValue("ui/companion_pose_keys", json.dumps(ui.companion_pose_keys))
        self._settings.setValue("ui/companion_rest_state", ui.companion_rest_state)
        self._settings.setValue("ui/companion_interval_seconds", ui.companion_interval_seconds)
        self._settings.remove("ui/companion_activity")
        self._settings.setValue("ui/companion_effects", ui.companion_effects)
        self._settings.setValue("ui/sprite_foot_overrides", json.dumps(ui.sprite_foot_overrides))

        # Save automation config
        automation = self._config.automation
        self._settings.setValue("automation/mouse_enabled", bool(automation.mouse_enabled))
        # Stored as a comma string, not a list: QSettings serializes an
        # empty list as an invalid variant that reads back None, which
        # _parse_class_list would resurrect as the default — making the
        # list impossible to clear. An empty string round-trips intact.
        self._settings.setValue(
            "automation/mouse_target_allowlist",
            ",".join(automation.mouse_target_allowlist),
        )
        self._settings.setValue("automation/a11y_enabled", bool(automation.a11y_enabled))
        self._settings.setValue(
            "automation/a11y_app_blacklist",
            ",".join(automation.a11y_app_blacklist),
        )
        self._settings.setValue(
            "automation/a11y_share_input_values",
            bool(automation.a11y_share_input_values),
        )
        self._settings.setValue(
            "automation/web_operation_enabled",
            bool(automation.web_operation_enabled),
        )

        # Save web config
        web = self._config.web
        self._settings.setValue("web/tavily_api_key", web.tavily_api_key)
        self._settings.setValue("web/verify_search_depth", web.verify_search_depth)

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
