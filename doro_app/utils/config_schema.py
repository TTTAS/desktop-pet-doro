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

    # History configuration
    history_turns: int = CHAT_DEFAULT_HISTORY_TURNS

    def __post_init__(self):
        """Validate configuration values."""
        # Validate timeout
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive integer, got {self.timeout_seconds}")

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
            raise ValueError(f"history_turns must be non-negative integer, got {self.history_turns}")

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

    @property
    def config_key_prefix(self) -> str:
        """QSettings key prefix for this config section."""
        return "ui"


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
            f"  app=AppConfig(current_state='{self.app.current_state}')\n"
            f")"
        )
