"""Application-level exceptions.

Centralized exception definitions for better error handling
and user feedback.
"""

from __future__ import annotations

from typing import Optional


class DoroError(Exception):
    """Base exception for all Doro application errors."""

    def __init__(self, message: str, user_message: Optional[str] = None):
        """
        Initialize Doro error.

        Args:
            message: Technical error message (for logging)
            user_message: User-friendly message (for display)
        """
        super().__init__(message)
        self.user_message = user_message or message


class StateError(DoroError):
    """Errors related to state operations."""

    pass


class StateNotFoundError(StateError):
    """Requested state does not exist."""

    def __init__(self, state_key: str):
        super().__init__(
            f"State '{state_key}' not found",
            f"找不到狀態 '{state_key}'",
        )
        self.state_key = state_key


class ProtectedStateError(StateError):
    """Attempt to modify/delete a protected state."""

    def __init__(self, state_key: str):
        super().__init__(
            f"Cannot modify protected state '{state_key}'",
            f"無法修改內建狀態 '{state_key}'",
        )
        self.state_key = state_key


class DuplicateStateError(StateError):
    """Attempt to create a state with existing key."""

    def __init__(self, state_key: str):
        super().__init__(
            f"State '{state_key}' already exists",
            f"狀態 '{state_key}' 已存在",
        )
        self.state_key = state_key


class GifError(DoroError):
    """Errors related to GIF operations."""

    pass


class GifNotFoundError(GifError):
    """GIF file not found."""

    def __init__(self, gif_path: str):
        super().__init__(
            f"GIF file not found: {gif_path}",
            "找不到 GIF 檔案",
        )
        self.gif_path = gif_path


class InvalidGifError(GifError):
    """Invalid or corrupted GIF file."""

    def __init__(self, gif_path: str):
        super().__init__(
            f"Invalid GIF file: {gif_path}",
            "GIF 檔案無效或損壞",
        )
        self.gif_path = gif_path


class GifStorageError(GifError):
    """Failed to store GIF file."""

    def __init__(self, reason: str):
        super().__init__(
            f"Failed to store GIF: {reason}",
            f"儲存 GIF 失敗：{reason}",
        )


class ChatError(DoroError):
    """Errors related to chat/LLM operations."""

    pass


class ChatConnectionError(ChatError):
    """Failed to connect to chat server."""

    def __init__(self, url: str, reason: str):
        super().__init__(
            f"Connection failed to {url}: {reason}",
            "無法連接到聊天伺服器",
        )
        self.url = url


class ChatTimeoutError(ChatError):
    """Chat request timed out."""

    def __init__(self, timeout_seconds: int):
        super().__init__(
            f"Chat request timed out after {timeout_seconds} seconds",
            f"聊天請求超時（{timeout_seconds} 秒）",
        )
        self.timeout_seconds = timeout_seconds


class ChatInvalidResponseError(ChatError):
    """Chat server returned invalid response."""

    def __init__(self, reason: str):
        super().__init__(
            f"Invalid response from chat server: {reason}",
            "聊天伺服器回應格式錯誤",
        )


class ConfigError(DoroError):
    """Errors related to configuration."""

    pass


class ConfigLoadError(ConfigError):
    """Failed to load configuration."""

    def __init__(self, config_file: str, reason: str):
        super().__init__(
            f"Failed to load config from {config_file}: {reason}",
            "無法載入設定檔",
        )
        self.config_file = config_file


class ConfigSaveError(ConfigError):
    """Failed to save configuration."""

    def __init__(self, config_file: str, reason: str):
        super().__init__(
            f"Failed to save config to {config_file}: {reason}",
            "無法儲存設定檔",
        )
        self.config_file = config_file


class MovementError(DoroError):
    """Errors related to movement operations."""

    pass


class InvalidDirectionError(MovementError):
    """Invalid movement direction."""

    def __init__(self, direction: str):
        super().__init__(
            f"Invalid movement direction: {direction}",
            f"無效的移動方向：{direction}",
        )
        self.direction = direction


class TransitionError(DoroError):
    """Errors related to state transitions."""

    pass


class TransitionNotFoundError(TransitionError):
    """Transition between states not found."""

    def __init__(self, from_state: str, to_state: str):
        super().__init__(
            f"No transition from '{from_state}' to '{to_state}'",
            f"沒有從 '{from_state}' 到 '{to_state}' 的過渡動畫",
        )
        self.from_state = from_state
        self.to_state = to_state


class TransitionInProgressError(TransitionError):
    """Attempt to change state during transition."""

    def __init__(self):
        super().__init__(
            "Cannot change state while transition is in progress",
            "過渡動畫進行中，無法切換狀態",
        )
