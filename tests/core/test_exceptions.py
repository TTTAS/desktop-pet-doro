"""Tests for application exceptions."""

from doro_app.core.exceptions import (
    ChatConnectionError,
    ChatTimeoutError,
    ConfigLoadError,
    ConfigSaveError,
    DoroError,
    DuplicateStateError,
    GifNotFoundError,
    InvalidGifError,
    ProtectedStateError,
    StateNotFoundError,
    TransitionInProgressError,
    TransitionNotFoundError,
)


class TestDoroError:
    """Tests for base DoroError."""

    def test_doro_error_basic(self):
        """Test basic DoroError creation."""
        error = DoroError("Technical message")
        assert str(error) == "Technical message"
        assert error.user_message == "Technical message"

    def test_doro_error_with_user_message(self):
        """Test DoroError with custom user message."""
        error = DoroError("Technical message", "User-friendly message")
        assert str(error) == "Technical message"
        assert error.user_message == "User-friendly message"


class TestStateErrors:
    """Tests for state-related errors."""

    def test_state_not_found_error(self):
        """Test StateNotFoundError."""
        error = StateNotFoundError("happy")
        assert "happy" in str(error)
        assert error.state_key == "happy"
        assert "找不到狀態" in error.user_message

    def test_protected_state_error(self):
        """Test ProtectedStateError."""
        error = ProtectedStateError("idle")
        assert "idle" in str(error)
        assert error.state_key == "idle"
        assert "無法修改內建狀態" in error.user_message

    def test_duplicate_state_error(self):
        """Test DuplicateStateError."""
        error = DuplicateStateError("happy")
        assert "happy" in str(error)
        assert error.state_key == "happy"
        assert "已存在" in error.user_message


class TestGifErrors:
    """Tests for GIF-related errors."""

    def test_gif_not_found_error(self):
        """Test GifNotFoundError."""
        error = GifNotFoundError("/path/to/missing.gif")
        assert "/path/to/missing.gif" in str(error)
        assert error.gif_path == "/path/to/missing.gif"
        assert "找不到" in error.user_message

    def test_invalid_gif_error(self):
        """Test InvalidGifError."""
        error = InvalidGifError("/path/to/corrupted.gif")
        assert "/path/to/corrupted.gif" in str(error)
        assert error.gif_path == "/path/to/corrupted.gif"
        assert "無效" in error.user_message


class TestChatErrors:
    """Tests for chat-related errors."""

    def test_chat_connection_error(self):
        """Test ChatConnectionError."""
        error = ChatConnectionError("http://localhost:1234", "Connection refused")
        assert "http://localhost:1234" in str(error)
        assert error.url == "http://localhost:1234"
        assert "無法連接" in error.user_message

    def test_chat_timeout_error(self):
        """Test ChatTimeoutError."""
        error = ChatTimeoutError(30)
        assert "30" in str(error)
        assert error.timeout_seconds == 30
        assert "超時" in error.user_message


class TestConfigErrors:
    """Tests for config-related errors."""

    def test_config_load_error(self):
        """Test ConfigLoadError."""
        error = ConfigLoadError("config.json", "File not found")
        assert "config.json" in str(error)
        assert error.config_file == "config.json"
        assert "無法載入" in error.user_message

    def test_config_save_error(self):
        """Test ConfigSaveError."""
        error = ConfigSaveError("config.json", "Permission denied")
        assert "config.json" in str(error)
        assert error.config_file == "config.json"
        assert "無法儲存" in error.user_message


class TestTransitionErrors:
    """Tests for transition-related errors."""

    def test_transition_not_found_error(self):
        """Test TransitionNotFoundError."""
        error = TransitionNotFoundError("idle", "happy")
        assert "idle" in str(error)
        assert "happy" in str(error)
        assert error.from_state == "idle"
        assert error.to_state == "happy"
        assert "過渡動畫" in error.user_message

    def test_transition_in_progress_error(self):
        """Test TransitionInProgressError."""
        error = TransitionInProgressError()
        assert "transition" in str(error).lower()
        assert "過渡動畫進行中" in error.user_message


class TestExceptionHierarchy:
    """Tests for exception inheritance."""

    def test_all_inherit_from_doro_error(self):
        """Test that all custom exceptions inherit from DoroError."""
        assert issubclass(StateNotFoundError, DoroError)
        assert issubclass(GifNotFoundError, DoroError)
        assert issubclass(ChatConnectionError, DoroError)
        assert issubclass(ConfigLoadError, DoroError)

    def test_can_catch_by_base_class(self):
        """Test that exceptions can be caught by base class."""
        try:
            raise StateNotFoundError("test")
        except DoroError as e:
            assert isinstance(e, StateNotFoundError)
            assert e.user_message is not None
