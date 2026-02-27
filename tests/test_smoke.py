"""
Smoke tests for Doro application.

Smoke tests verify basic functionality - "does it run without crashing?"
These are NOT detailed unit tests. They check:
1. Can components be created?
2. Do basic operations work?
3. Does the app crash on startup?

Think of smoke tests as "turn it on, does it smoke?" tests.
"""

import pytest
from pathlib import Path

try:
    from PySide6 import QtCore
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

pytestmark = pytest.mark.skipif(not HAS_PYSIDE6, reason="PySide6 not available")


class TestStateServiceSmoke:
    """Smoke tests for StateService - basic operations only."""

    @pytest.fixture
    def state_service(self, tmp_path):
        """Create a StateService instance for testing."""
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )

        # Create repositories
        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_list_path = tmp_path / "state_list.txt"

        # Create service
        return StateService(state_repo, move_repo, gif_repo, state_list_path)

    def test_state_service_can_be_created(self, state_service):
        """StateService can be initialized without crashing."""
        # Just create it - if this crashes, something is very wrong
        assert state_service is not None

    def test_can_add_and_retrieve_state(self, state_service):
        """Basic state operations work."""
        # Add a state
        state_service.add_state("happy", "Happy State")

        # Can we get it back?
        state = state_service.get_state("happy")
        assert state is not None
        assert state.key == "happy"

    def test_can_set_current_state(self, state_service):
        """Can set and retrieve current state."""
        state_service.add_state("idle", "Idle")

        # Set current state
        result = state_service.set_state("idle")
        assert result is True

        # Can we get it back?
        current = state_service.get_current_state_key()
        assert current == "idle"

    def test_can_save_and_load_states(self, tmp_path):
        """States can be persisted to disk."""
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )

        # Create service, add state, save
        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_list_path = tmp_path / "state_list.txt"

        service = StateService(state_repo, move_repo, gif_repo, state_list_path)
        service.add_state("test", "Test State")
        service.save_states()

        # Create new service, load
        state_repo2 = StateRepository(tmp_path / "states.json")
        move_repo2 = MoveStateRepository(tmp_path / "moves.json")
        gif_repo2 = GifRepository(tmp_path / "resources")

        service2 = StateService(state_repo2, move_repo2, gif_repo2, state_list_path)
        # Need to call initialize() to load states from disk
        service2.initialize()

        # Check if state persisted
        state = service2.get_state("test")
        assert state is not None


class TestChatControllerSmoke:
    """Smoke tests for ChatController - initialization only."""

    def test_chat_controller_can_be_created(self, tmp_path):
        """ChatController can be initialized without crashing."""
        from doro_app.core.chat.controller import ChatController
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )
        from doro_app.utils.config_manager import ConfigManager

        # Create ConfigManager
        config_path = tmp_path / "config.toml"
        config_manager = ConfigManager(config_path)

        # Create a temporary prompt file
        prompt_path = tmp_path / "system_prompt.txt"
        prompt_path.write_text("You are a helpful assistant.")

        # Create state service (required for ChatController)
        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_service = StateService(state_repo, move_repo, gif_repo, tmp_path / "state_list.txt")

        # This should not crash
        controller = ChatController(
            prompt_path=prompt_path,
            state_service=state_service,
            state_text_provider=lambda: "States: idle, happy",
            movement_hint_provider=lambda: "Movement: none",
            config_manager=config_manager,
        )
        assert controller is not None

    def test_chat_controller_has_basic_properties(self, tmp_path):
        """ChatController has expected properties."""
        from doro_app.core.chat.controller import ChatController
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )
        from doro_app.utils.config_manager import ConfigManager

        # Create ConfigManager
        config_path = tmp_path / "config.toml"
        config_manager = ConfigManager(config_path)

        prompt_path = tmp_path / "system_prompt.txt"
        prompt_path.write_text("Test prompt")

        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_service = StateService(state_repo, move_repo, gif_repo, tmp_path / "state_list.txt")

        controller = ChatController(
            prompt_path=prompt_path,
            state_service=state_service,
            state_text_provider=lambda: "",
            movement_hint_provider=lambda: "",
            config_manager=config_manager,
        )

        # Basic properties should exist and have defaults
        assert controller.server_url is not None
        assert controller.model is not None
        assert controller.temperature > 0

    def test_uses_qrunnable_not_qtconcurrent(self):
        """
        Test that ChatController uses QRunnable + QThreadPool (official PySide6 pattern).

        QtConcurrent.run is not available in PySide6 because it's template-based.
        The official pattern is to use QRunnable with signals for background tasks.

        This test ensures the code follows the official PySide6 approach.
        """
        import inspect
        from doro_app.core.chat.controller import ChatController, ChatWorker, ChatWorkerSignals

        # Verify ChatWorker exists and is a QRunnable
        from PySide6.QtCore import QRunnable, QObject
        assert issubclass(ChatWorker, QRunnable), "ChatWorker should inherit from QRunnable"

        # Verify ChatWorkerSignals exists and is a QObject (needed for signals)
        assert issubclass(ChatWorkerSignals, QObject), "ChatWorkerSignals should inherit from QObject"

        # Get source code of start_request method
        source = inspect.getsource(ChatController.start_request)

        # Verify it uses QThreadPool (official Qt pattern)
        assert "self._pool.start" in source, \
            "start_request should use self._pool.start (QThreadPool)"

        # Verify it does NOT use QtConcurrent.run (not available in PySide6)
        assert "QtConcurrent.run" not in source, \
            "start_request should NOT use QtConcurrent.run (not available in PySide6)"

        # Verify it uses ChatWorker
        assert "ChatWorker" in source, \
            "start_request should create ChatWorker instances"


class TestMovementManagerSmoke:
    """Smoke tests for MovementManager - basic operations."""

    def test_movement_manager_can_be_created(self, tmp_path):
        """MovementManager can be initialized."""
        from doro_app.core.movement.manager import MovementManager
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )
        from unittest.mock import Mock

        # Create mock window
        mock_window = Mock()
        mock_window.pos.return_value = QtCore.QPoint(100, 100)
        mock_window.size.return_value = QtCore.QSize(400, 300)

        # Create state service
        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_service = StateService(state_repo, move_repo, gif_repo, tmp_path / "state_list.txt")

        # This should not crash
        manager = MovementManager(
            window=mock_window,
            state_service=state_service,
            movement_step_px=60,
        )
        assert manager is not None

    def test_movement_instruction_text_loads(self, tmp_path):
        """Movement instruction text can be loaded."""
        from doro_app.core.movement.manager import MovementManager
        from doro_app.core.state import StateService
        from doro_app.core.state.repository import (
            StateRepository,
            MoveStateRepository,
            GifRepository,
        )
        from unittest.mock import Mock

        mock_window = Mock()

        # Create state service
        state_repo = StateRepository(tmp_path / "states.json")
        move_repo = MoveStateRepository(tmp_path / "moves.json")
        gif_repo = GifRepository(tmp_path / "resources")
        state_service = StateService(state_repo, move_repo, gif_repo, tmp_path / "state_list.txt")

        manager = MovementManager(mock_window, state_service, 60)

        # Should return instruction text (not empty)
        instructions = manager.instruction_text()
        assert instructions is not None
        assert len(instructions) > 0


class TestContextMenuSmoke:
    """Smoke tests for context menu - ensure right-click menu works."""

    def test_themed_menu_module_imports(self):
        """Themed menu module can be imported without errors."""
        from doro_app.ui.theme import themed_menu

        # Check that key functions exist
        assert hasattr(themed_menu, 'create_doro_menu')
        assert hasattr(themed_menu, 'build_context_menu_content')
        assert hasattr(themed_menu, 'DoroMenu')

    def test_build_context_menu_accesses_correct_attributes(self):
        """
        Test that build_context_menu_content accesses the correct CoreManager properties.

        This test ensures that after the refactoring (removing _chat_orchestrator and
        _chat_controller from Window), the menu building code uses the correct API.
        """
        from unittest.mock import Mock
        import inspect
        from doro_app.ui.theme.themed_menu import build_context_menu_content

        # Get the source code of build_context_menu_content
        source = inspect.getsource(build_context_menu_content)

        # Verify it uses CoreManager's public API (not removed attributes)
        assert "_core_manager.is_chat_inflight" in source, \
            "Menu should use window._core_manager.is_chat_inflight"
        assert "_core_manager.has_chat_history" in source, \
            "Menu should use window._core_manager.has_chat_history"

        # Verify it does NOT use the removed attributes
        assert "_chat_orchestrator.is_inflight" not in source, \
            "Menu should NOT use window._chat_orchestrator (removed in refactoring)"
        assert "_chat_controller.has_history" not in source, \
            "Menu should NOT use window._chat_controller (removed in refactoring)"

    def test_context_menu_exec_compatibility(self):
        """
        Test that contextMenuEvent handles exec/exec_() compatibility.

        PySide6 versions differ in QMenu method names:
        - Newer: menu.exec(pos)
        - Older: menu.exec_(pos)

        This test ensures the window handles both cases.
        """
        import inspect
        from doro_app.ui.window import DoroWindow

        # Get the source code of contextMenuEvent
        source = inspect.getsource(DoroWindow.contextMenuEvent)

        # Verify it handles exec/exec_ compatibility
        assert ("hasattr(menu, 'exec')" in source or "hasattr(menu, \"exec\")" in source), \
            "contextMenuEvent should check for exec availability"
        assert ("exec_" in source), \
            "contextMenuEvent should fall back to exec_() for compatibility"


class TestMouseEventHandlingSmoke:
    """Smoke tests for mouse event handling - ensure left/right click work."""

    def test_mouse_event_handler_can_be_created(self):
        """MouseEventHandler can be initialized."""
        from doro_app.ui.events.mouse_event_handler import MouseEventHandler
        from unittest.mock import Mock

        mock_bubble = Mock()
        handler = MouseEventHandler(bubble_controller=mock_bubble, click_threshold=5)
        assert handler is not None

    def test_mouse_press_event_handles_left_button(self):
        """MouseEventHandler handles left button press."""
        from doro_app.ui.events.mouse_event_handler import MouseEventHandler
        from PySide6 import QtCore, QtGui
        from unittest.mock import Mock

        mock_bubble = Mock()
        mock_bubble.begin_transform.return_value = False

        handler = MouseEventHandler(bubble_controller=mock_bubble)

        # Create mock mouse event
        mock_event = Mock(spec=QtGui.QMouseEvent)
        mock_event.button.return_value = QtCore.Qt.MouseButton.LeftButton
        mock_event.position.return_value = QtCore.QPointF(100, 100)
        mock_event.globalPosition.return_value = QtCore.QPointF(500, 500)

        mock_geometry = QtCore.QRect(400, 400, 200, 200)

        # Should handle the event
        result = handler.handle_press(mock_event, mock_geometry)
        assert result is True

    def test_mouse_press_event_ignores_right_button(self):
        """MouseEventHandler ignores right button (for context menu)."""
        from doro_app.ui.events.mouse_event_handler import MouseEventHandler
        from PySide6 import QtCore, QtGui
        from unittest.mock import Mock

        mock_bubble = Mock()
        handler = MouseEventHandler(bubble_controller=mock_bubble)

        # Create mock right-click event
        mock_event = Mock(spec=QtGui.QMouseEvent)
        mock_event.button.return_value = QtCore.Qt.MouseButton.RightButton

        mock_geometry = QtCore.QRect(400, 400, 200, 200)

        # Should NOT handle the event (returns False to allow context menu)
        result = handler.handle_press(mock_event, mock_geometry)
        assert result is False


class TestConstantsSmoke:
    """Smoke test for constants - ensure they're all defined."""

    def test_all_critical_constants_exist(self):
        """All newly added constants are importable."""
        from doro_app.constants import (
            # Color
            COLOR_ALPHA_MAX,
            # Chat
            CHAT_DEFAULT_HISTORY_TURNS,
            CHAT_DEFAULT_TIMEOUT_SECONDS,
            CHAT_DEFAULT_TEMPERATURE,
            CHAT_DEFAULT_MAX_TOKENS,
            CHAT_CONFIG_PERSIST_DELAY_MS,
            CHAT_THREAD_CLEANUP_DELAY_MS,
            # Movement
            MOVEMENT_SPEED_SLOW,
            MOVEMENT_SPEED_MEDIUM,
            MOVEMENT_SPEED_FAST,
            # Bubble
            BUBBLE_SCALE_MIN,
            BUBBLE_SCALE_MAX,
            # UI Layout
            PANEL_MIN_WIDTH,
            PANEL_MIN_HEIGHT,
            PANEL_PADDING,
            PANEL_MAX_WIDTH,
            # Screen/Window
            FALLBACK_SCREEN_WIDTH,
            FALLBACK_SCREEN_HEIGHT,
            WINDOW_INITIAL_POSITION_OFFSET_X,
            WINDOW_INITIAL_POSITION_OFFSET_Y,
        )

        # If any constant is missing, this test will fail at import time
        # Just check they have reasonable values
        assert COLOR_ALPHA_MAX == 255
        assert CHAT_DEFAULT_HISTORY_TURNS > 0
        assert MOVEMENT_SPEED_SLOW < MOVEMENT_SPEED_MEDIUM < MOVEMENT_SPEED_FAST
        assert BUBBLE_SCALE_MIN < BUBBLE_SCALE_MAX
        assert PANEL_MIN_WIDTH > 0
        assert FALLBACK_SCREEN_WIDTH > 0
