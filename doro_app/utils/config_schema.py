"""Type-safe configuration schema using dataclasses.

This module defines the structure of all application configuration.
Each dataclass represents a logical grouping of related settings.

Benefits:
- Type safety: IDE autocomplete and type checking
- Validation: Invalid values caught early
- Single source of truth: All config keys defined here
- Discoverability: config.chat.timeout_seconds (not "chat/timeout_seconds")
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    DEFAULT_TAVILY_API_KEY,
    DEFAULT_VERIFY_SEARCH_DEPTH,
    DEFAULT_WEB_OPERATION_ENABLED,
    STRUCTURED_MODES,
)

# ═══════════════════════════════════════════════════════════
# Configuration Dataclasses
# ═══════════════════════════════════════════════════════════


@dataclass
class ChatConfig:
    """
    Chat/LLM configuration.

    Controls how the application communicates with language model APIs.
    """

    # Server configuration
    server_url: str = DEFAULT_CHAT_SERVER_URL
    model: str = DEFAULT_CHAT_MODEL
    endpoint_path: str = DEFAULT_CHAT_ENDPOINT_PATH
    api_key: str = DEFAULT_CHAT_API_KEY

    # Request configuration
    timeout_seconds: int = CHAT_DEFAULT_TIMEOUT_SECONDS
    temperature: float = CHAT_DEFAULT_TEMPERATURE
    max_tokens: int = CHAT_DEFAULT_MAX_TOKENS
    max_retries: int = DEFAULT_CHAT_MAX_RETRIES

    # Stop tokens
    stop_tokens: list[str] = field(default_factory=lambda: list(DEFAULT_CHAT_STOP_TOKENS))
    max_stop_tokens: int = DEFAULT_CHAT_MAX_STOP_TOKENS

    # History configuration
    history_turns: int = CHAT_DEFAULT_HISTORY_TURNS

    # 結構化回覆模式（auto / json_schema / text）
    structured_mode: str = DEFAULT_CHAT_STRUCTURED_MODE

    def __post_init__(self):
        """Validate configuration values."""
        # Validate timeout
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be positive integer, got {self.timeout_seconds}"
            )

        # Validate temperature
        if not isinstance(self.temperature, (int, float)) or not (0.0 <= self.temperature <= 2.0):
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")

        # Validate max_tokens
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive integer, got {self.max_tokens}")

        # Validate max_retries
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative integer, got {self.max_retries}")

        # Validate history_turns
        if not isinstance(self.history_turns, int) or self.history_turns < 0:
            raise ValueError(
                f"history_turns must be non-negative integer, got {self.history_turns}"
            )

        if self.structured_mode not in STRUCTURED_MODES:
            raise ValueError(
                f"structured_mode must be one of {STRUCTURED_MODES}, got {self.structured_mode!r}"
            )

    @property
    def config_key_prefix(self) -> str:
        """QSettings key prefix for this config section."""
        return "chat"


@dataclass
class UIConfig:
    """
    UI appearance configuration.

    Controls visual elements like bubble position and scale.
    """

    # Bubble positioning
    bubble_offset_x: float = BUBBLE_DEFAULT_OFFSET_X
    bubble_offset_y: float = BUBBLE_DEFAULT_OFFSET_Y

    # Bubble appearance
    bubble_scale: float = BUBBLE_DEFAULT_SCALE
    quiet_companion: bool = False
    companion_home_x: float = 0.9
    companion_home_y: float | None = None  # None means no saved resting point.
    companion_rest_state: str = "idle"
    companion_interval_seconds: int = 9
    companion_effects: bool = True
    companion_pose_keys: list[str] = field(default_factory=lambda: ["happy"])
    sprite_foot_overrides: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration values."""
        # Offsets can be any float (positive or negative)
        if not isinstance(self.bubble_offset_x, (int, float)):
            raise ValueError(f"bubble_offset_x must be numeric, got {self.bubble_offset_x}")

        if not isinstance(self.bubble_offset_y, (int, float)):
            raise ValueError(f"bubble_offset_y must be numeric, got {self.bubble_offset_y}")

        # Scale should be positive
        if not isinstance(self.bubble_scale, (int, float)) or self.bubble_scale <= 0:
            raise ValueError(f"bubble_scale must be positive number, got {self.bubble_scale}")
        if not isinstance(self.quiet_companion, bool):
            raise ValueError("quiet_companion must be bool")
        if (
            not isinstance(self.companion_home_x, (int, float))
            or not 0 <= self.companion_home_x <= 1
        ):
            raise ValueError("companion_home_x must be between 0 and 1")
        if self.companion_home_y is not None and (
            not isinstance(self.companion_home_y, (int, float))
            or isinstance(self.companion_home_y, bool)
            or not 0 <= self.companion_home_y <= 1
        ):
            raise ValueError("companion_home_y must be None or between 0 and 1")
        if not isinstance(self.companion_rest_state, str) or not self.companion_rest_state.strip():
            raise ValueError("companion_rest_state must be a nonempty state key")
        if (
            type(self.companion_interval_seconds) is not int
            or not 1 <= self.companion_interval_seconds <= 3600
        ):
            raise ValueError("companion_interval_seconds must be an integer from 1 to 3600")
        if not isinstance(self.companion_effects, bool):
            raise ValueError("companion_effects must be bool")
        if not isinstance(self.companion_pose_keys, list) or any(
            not isinstance(key, str) or not key.strip() for key in self.companion_pose_keys
        ):
            raise ValueError("companion_pose_keys must be a list of nonempty state keys")
        if not isinstance(self.sprite_foot_overrides, dict) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 <= value <= 1
            for key, value in self.sprite_foot_overrides.items()
        ):
            raise ValueError("sprite_foot_overrides must map GIF paths to ratios")

    @property
    def config_key_prefix(self) -> str:
        """QSettings key prefix for this config section."""
        return "ui"


@dataclass
class AutomationConfig:
    """Phase 1c automation configuration (restricted synthetic mouse clicks).

    Defaults are conservative: `mouse_enabled=False` means no synthetic
    events will ever fire even if the LLM emits `[mouse:click]`. The
    allowlist gates which foreground-window classes are considered
    valid click targets at the moment of firing.
    """

    mouse_enabled: bool = False
    mouse_target_allowlist: tuple[str, ...] = DEFAULT_MOUSE_TARGET_ALLOWLIST
    # Phase 1d: read the foreground window's accessibility tree into the
    # prompt. Independent opt-in from `mouse_enabled`.
    a11y_enabled: bool = DEFAULT_A11Y_ENABLED
    a11y_app_blacklist: tuple[str, ...] = DEFAULT_A11Y_APP_BLACKLIST
    # Phase 1d follow-up: even when a11y is on, input-field values are
    # redacted by default (URL bar, search box, half-typed text). The
    # user can opt in via the settings dialog.
    a11y_share_input_values: bool = DEFAULT_A11Y_SHARE_INPUT_VALUES
    # 網頁操作（第 3 層）總開關。預設關：doro 只有在這打開時，才准「明講的」
    # 操作指令去點/填/送出網頁（送出類仍會逐一問使用者）。跟 mouse/a11y 同樣是
    # 保守的 opt-in。
    web_operation_enabled: bool = DEFAULT_WEB_OPERATION_ENABLED

    def __post_init__(self):
        if not isinstance(self.mouse_enabled, bool):
            raise ValueError(f"mouse_enabled must be bool, got {type(self.mouse_enabled)}")
        if not isinstance(self.mouse_target_allowlist, (tuple, list)):
            raise ValueError(
                f"mouse_target_allowlist must be tuple/list, got {type(self.mouse_target_allowlist)}"
            )
        if not isinstance(self.a11y_enabled, bool):
            raise ValueError(f"a11y_enabled must be bool, got {type(self.a11y_enabled)}")
        if not isinstance(self.a11y_app_blacklist, (tuple, list)):
            raise ValueError(
                f"a11y_app_blacklist must be tuple/list, got {type(self.a11y_app_blacklist)}"
            )
        if not isinstance(self.a11y_share_input_values, bool):
            raise ValueError(
                f"a11y_share_input_values must be bool, got {type(self.a11y_share_input_values)}"
            )
        if not isinstance(self.web_operation_enabled, bool):
            raise ValueError(
                f"web_operation_enabled must be bool, got {type(self.web_operation_enabled)}"
            )
        # Normalize to tuple of stripped non-empty strings
        normalized = tuple(
            str(item).strip() for item in self.mouse_target_allowlist if str(item).strip()
        )
        object.__setattr__(self, "mouse_target_allowlist", normalized)
        normalized_blacklist = tuple(
            str(item).strip() for item in self.a11y_app_blacklist if str(item).strip()
        )
        object.__setattr__(self, "a11y_app_blacklist", normalized_blacklist)

    @property
    def config_key_prefix(self) -> str:
        return "automation"


@dataclass
class WebConfig:
    """Web / verify (search API) configuration.

    Holds the Tavily API key and verify search depth. Deliberately a
    SEPARATE section from ChatConfig so the search key never shares a
    slot with the LLM endpoint key (chat.api_key).
    """

    tavily_api_key: str = DEFAULT_TAVILY_API_KEY
    verify_search_depth: str = DEFAULT_VERIFY_SEARCH_DEPTH

    def __post_init__(self):
        if not isinstance(self.tavily_api_key, str):
            raise ValueError(f"tavily_api_key must be str, got {type(self.tavily_api_key)}")
        self.tavily_api_key = self.tavily_api_key.strip()
        depth = str(self.verify_search_depth).strip().lower()
        if depth not in ("basic", "advanced"):
            depth = "basic"
        self.verify_search_depth = depth

    @property
    def config_key_prefix(self) -> str:
        return "web"


@dataclass
class AppConfig:
    """
    Application-level configuration.

    State and session management settings.
    """

    # Current application state
    current_state: str = "idle"

    def __post_init__(self):
        """Validate configuration values."""
        if not isinstance(self.current_state, str) or not self.current_state.strip():
            raise ValueError(f"current_state must be non-empty string, got {self.current_state}")

        # Normalize whitespace
        self.current_state = self.current_state.strip()

    @property
    def config_key_prefix(self) -> str:
        """QSettings key prefix for this config section."""
        return ""  # Root level, no prefix


# ═══════════════════════════════════════════════════════════
# Combined Configuration
# ═══════════════════════════════════════════════════════════


@dataclass
class DoroConfig:
    """
    Complete application configuration.

    Aggregates all configuration sections into a single object.
    """

    chat: ChatConfig = field(default_factory=ChatConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    app: AppConfig = field(default_factory=AppConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def __repr__(self) -> str:
        """Readable representation of configuration."""
        return (
            f"DoroConfig(\n"
            f"  chat=ChatConfig(\n"
            f"    server_url='{self.chat.server_url}',\n"
            f"    model='{self.chat.model}',\n"
            f"    temperature={self.chat.temperature},\n"
            f"    timeout={self.chat.timeout_seconds}s,\n"
            f"    history_turns={self.chat.history_turns}\n"
            f"  ),\n"
            f"  ui=UIConfig(\n"
            f"    offset=({self.ui.bubble_offset_x}, {self.ui.bubble_offset_y}),\n"
            f"    scale={self.ui.bubble_scale}\n"
            f"  ),\n"
            f"  app=AppConfig(current_state='{self.app.current_state}'),\n"
            f"  web=WebConfig(has_key={bool(self.web.tavily_api_key)}, "
            f"depth='{self.web.verify_search_depth}')\n"
            f")"
        )
