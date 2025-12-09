"""Main application window and UI logic for Doro."""

from __future__ import annotations

import time
from typing import Optional, Protocol

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    TIMER_INTERVAL_MS,
    BUBBLE_AUTO_HIDE_MS,
    WINDOW_INITIAL_WIDTH,
    WINDOW_INITIAL_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    SPRITE_DEFAULT_WIDTH,
    SPRITE_DEFAULT_HEIGHT,
    SPRITE_OFFSET_X,
    PANEL_DEFAULT_WIDTH_HINT,
    PANEL_DEFAULT_HEIGHT_HINT,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
    MOVEMENT_ONLY_STATE_KEYS,
    DEFAULT_MOVE_STATE_KEY,
    CLICK_DRAG_THRESHOLD_PX,
    WINDOW_INITIAL_POSITION_OFFSET_X,
    WINDOW_INITIAL_POSITION_OFFSET_Y,
)
from .components.bubble_controller import BubbleConfig, BubbleController
from .components.gif_player import GifPlayer
from .rendering.design_tokens import tokens
from .rendering.rendering_engine import RenderingEngine
from .events.mouse_event_handler import MouseEventHandler
from .layout.layout_manager import WindowLayoutManager
from .viewmodels.doro_viewmodel import DoroViewModel
# NOTE: Removed imports for TransitionPlayer, MovementManager, ChatController, ChatOrchestrator
# These are now accessed through CoreManager
from ..utils.logger import get_logger
from ..utils.models import MoveStateSettings
from ..core.state import StateService
from .theme.theme import ensure_application_theme
from .theme.themed_menu import build_context_menu_content, create_doro_menu
from .helpers import ChatUIHelper
from ..utils.config_manager import ConfigManager
from ..utils.utils import safe_float as _safe_float

logger = get_logger(__name__)


class MovementWindowPort(Protocol):
    """Interface for movement-related window operations."""

    def frameGeometry(self) -> QtCore.QRect:  # pragma: no cover - Qt binding
        ...

    def current_position(self) -> QtCore.QPoint: ...

    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint: ...

    def move_window_to(self, pos: QtCore.QPoint): ...

    def get_bubble_offset(self) -> QtCore.QPointF: ...

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False): ...

    def reset_tick_timer(self, value: float): ...


class DoroWindow(QtWidgets.QWidget):
    def __init__(
        self,
        state_service: StateService,
        config: QtCore.QSettings,
        not_topmost: bool = False,
        config_manager: ConfigManager | None = None,
    ):
        """
        Initialize the Doro window (UI layer only).

        Args:
            state_service: State management service (injected)
            config: (Legacy) QSettings for configuration
            not_topmost: If True, window will not stay on top
            config_manager: ConfigManager for type-safe config access

        Note:
            Managers and controllers are wired after construction via wire_dependencies().
            This is due to circular dependencies that will be resolved in Phase 3.
        """
        super().__init__()
        logger.info("Initializing Doro window")
        ensure_application_theme()

        # ─────────────────────────────────────────────────────────
        # Qt Widget Setup
        # ─────────────────────────────────────────────────────────
        self.resize(WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool  # hides from taskbar
        )
        if not not_topmost:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # ─────────────────────────────────────────────────────────
        # Injected Dependencies
        # ─────────────────────────────────────────────────────────
        self._state_service = state_service
        self._config = config  # Legacy QSettings
        self._config_manager = config_manager  # New: Type-safe config

        # File paths (reconstructed from constants)
        from ..utils.paths import STATE_DIR

        self._default_idle_gif = STATE_DIR / "idle.gif"

        # NOTE: StateController now handles state change callbacks
        # (previously set here, now done in StateController.__init__)

        # ─────────────────────────────────────────────────────────
        # Dependencies wired later (due to circular dependency)
        # ─────────────────────────────────────────────────────────
        # Controllers
        self._state_controller = None
        self._gif_controller = None
        self._dialog_manager = None
        self._click_action_controller = None
        # Managers
        self._bubble_controller: BubbleController | None = None
        self._core_manager = None  # Will be set by DoroApp
        # Event handlers
        self._mouse_handler: MouseEventHandler | None = None
        # NOTE: _transition_player, _movement, _chat_controller, _chat_orchestrator removed
        # These are now accessed through _core_manager

        # ─────────────────────────────────────────────────────────
        # ViewModel (Presentation State)
        # ─────────────────────────────────────────────────────────
        self._view_model = DoroViewModel()
        self._view_model.set_sprite_size(QtCore.QSize(SPRITE_DEFAULT_WIDTH, SPRITE_DEFAULT_HEIGHT))
        self._view_model.set_sprite_offset_x(SPRITE_OFFSET_X)

        # ─────────────────────────────────────────────────────────
        # Rendering Engine
        # ─────────────────────────────────────────────────────────
        self._rendering_engine = RenderingEngine(self._view_model)

        # ─────────────────────────────────────────────────────────
        # Animation Timer
        # ─────────────────────────────────────────────────────────
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TIMER_INTERVAL_MS)

        # ─────────────────────────────────────────────────────────
        # UI State Variables
        # ─────────────────────────────────────────────────────────
        self._current_state_key: str = ""
        self._previous_state_key: Optional[str] = None  # Track previous state for transitions
        self._state_list_text: str = ""
        self._movement_only_state_keys: set[str] = MOVEMENT_ONLY_STATE_KEYS
        self._move_state_list_text: str = ""

        self._gif_player = GifPlayer()
        self._gif_movie: QtGui.QMovie | None = None

        self._bubble_text = ""
        self._bubble_text_show_override = False
        self._bubble_auto_hide_ms = BUBBLE_AUTO_HIDE_MS
        self._last_user_activity = time.monotonic()
        self._bubble_offset = QtCore.QPointF(BUBBLE_DEFAULT_OFFSET_X, BUBBLE_DEFAULT_OFFSET_Y)

        self._panel_width_hint = PANEL_DEFAULT_WIDTH_HINT
        self._panel_height_hint = PANEL_DEFAULT_HEIGHT_HINT
        self._panel_rect_cache: QtCore.QRectF | None = None
        self._sprite_anchor_top: float | None = None

        self._default_move_state_key = DEFAULT_MOVE_STATE_KEY
        self._sizing_in_progress = False
        self._last_tick_time = time.monotonic()

        # ─────────────────────────────────────────────────────────
        # Chat UI Helper
        # ─────────────────────────────────────────────────────────
        self._chat_ui = ChatUIHelper(self)
        self._chat_cursor_overridden = False

        # ─────────────────────────────────────────────────────────
        # Apply UI Preferences from Config
        # ─────────────────────────────────────────────────────────
        self._apply_window_preferred_size()

        # ─────────────────────────────────────────────────────────
        # Context Menu and Window Positioning
        # ─────────────────────────────────────────────────────────
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        # Place near bottom-right of primary screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(
                g.right() - self.width() - WINDOW_INITIAL_POSITION_OFFSET_X,
                g.bottom() - self.height() - WINDOW_INITIAL_POSITION_OFFSET_Y,
            )

        self.setWindowTitle("doro")

    @property
    def view_model(self):
        """Get ViewModel (needed by controllers)."""
        return self._view_model

    @property
    def state_list_text(self) -> str:
        """Get current state list text (used by ChatController)."""
        return self._state_list_text or ""

    def wire_dependencies(
        self,
        state_controller,
        gif_controller,
        dialog_manager,
        click_action_controller,
        bubble_controller: BubbleController,
    ):
        """
        Wire UI-layer dependencies after window construction.

        NOTE: This method is being phased out. Component storage and most signal
        connections are now handled in DoroApp. Only UI-specific wiring remains here.

        Args:
            state_controller: Coordinates state changes with ViewModel
            gif_controller: Handles GIF loading and playback
            dialog_manager: Manages dialog windows
            click_action_controller: Handles click actions
            bubble_controller: Manages bubble UI state
        """
        # NOTE: Component storage is now done in DoroApp._connect_ui_controllers()
        # These are kept for backward compatibility during transition

        # ─────────────────────────────────────────────────────────
        # Create and wire event handlers (UI-specific)
        # ─────────────────────────────────────────────────────────
        self._mouse_handler = MouseEventHandler(
            bubble_controller=bubble_controller, click_threshold=CLICK_DRAG_THRESHOLD_PX
        )
        self._mouse_handler.window_drag_requested.connect(self.move)
        self._mouse_handler.click_detected.connect(
            lambda: (
                self._mark_user_activity(),
                click_action_controller.trigger_random_action(),
            )
        )
        self._mouse_handler.user_activity_detected.connect(self._mark_user_activity)

        # ─────────────────────────────────────────────────────────
        # Connect UI controller signals (not handled by DoroApp yet)
        # ─────────────────────────────────────────────────────────
        state_controller.repaint_requested.connect(self.update)
        # NOTE: state_changed connection is also in DoroApp (duplicate, will be removed)
        state_controller.state_list_updated.connect(self._on_state_list_updated)

        gif_controller.repaint_requested.connect(self.update)
        gif_controller.gif_loaded.connect(self._on_gif_loaded)
        gif_controller.sprite_size_changed.connect(self._on_sprite_size_changed)

        # NOTE: TransitionPlayer and ChatOrchestrator connections removed
        # These are now handled through CoreManager in DoroApp

        # ─────────────────────────────────────────────────────────
        # Apply configuration
        # ─────────────────────────────────────────────────────────
        if self._config_manager:
            # Use ConfigManager for type-safe config access
            offset_x = self._config_manager.ui.bubble_offset_x
            offset_y = self._config_manager.ui.bubble_offset_y
            scale_pref = self._config_manager.ui.bubble_scale
        else:
            # Fallback to legacy QSettings
            offset_x = _safe_float(
                self._config.value("ui/bubble_offset_x", BUBBLE_DEFAULT_OFFSET_X),
                BUBBLE_DEFAULT_OFFSET_X,
            )
            offset_y = _safe_float(
                self._config.value("ui/bubble_offset_y", BUBBLE_DEFAULT_OFFSET_Y),
                BUBBLE_DEFAULT_OFFSET_Y,
            )
            scale_pref = _safe_float(
                self._config.value("ui/bubble_scale", BUBBLE_DEFAULT_SCALE), BUBBLE_DEFAULT_SCALE
            )

        self._bubble_controller.apply_persisted_config(
            BubbleConfig(
                offset_x=offset_x,
                offset_y=offset_y,
                scale=scale_pref,
                auto_hide_ms=self._bubble_auto_hide_ms,
            )
        )

    # ─────────────────────────────────────────────────────────
    # Controller signal handlers
    # ─────────────────────────────────────────────────────────

    def _load_state_gif(self, state_key: str):
        """
        Load the GIF for a given state.

        Args:
            state_key: The state key to load GIF for
        """
        gif_resource_id = self._state_service.get_gif_id(state_key)
        if gif_resource_id:
            gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
            if gif_path:
                self._gif_controller.load_gif(str(gif_path))

    def _on_controller_state_changed(self, state_key: str):
        """
        Handle state change from StateController.

        StateController handles ViewModel updates, we handle transitions and GIF loading.
        """
        # Track previous state for transition detection
        old_state_key = self._previous_state_key
        self._previous_state_key = state_key
        self._current_state_key = state_key

        # Skip transition on initial load (no previous state)
        if old_state_key is None:
            logger.debug(f"Initial state load: {state_key}")
            self._load_state_gif(state_key)
            return

        # Skip transition if same state
        if old_state_key == state_key:
            logger.debug(f"Same state, no transition needed: {state_key}")
            return

        # Check if transition exists and play it (through CoreManager)
        if self._core_manager.transition_player.play_transition(old_state_key, state_key):
            # Transition is playing, TransitionPlayer will load target GIF after completion
            logger.debug(f"Playing transition: {old_state_key} -> {state_key}")
        else:
            # No transition, load GIF directly
            logger.debug(f"No transition, loading GIF directly: {old_state_key} -> {state_key}")
            self._load_state_gif(state_key)

    def _on_state_list_updated(self, state_list_text: str):
        """Handle state list update from StateController."""
        self._state_list_text = state_list_text

    def _on_gif_loaded(self, movie):
        """Handle GIF loaded from GifController."""
        self._gif_movie = movie

    def _on_sprite_size_changed(self, size):
        """Handle sprite size change from GifController."""
        self._apply_window_preferred_size()

    # --- Animation -------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        dt = now - getattr(self, "_last_tick_time", now)
        self._last_tick_time = now
        if dt < 0.0:
            dt = 0.0
        dt = min(dt, tokens.animation.max_delta_time)

        # Process movement through CoreManager
        self._core_manager.process_movement_tick(dt)

        # NEW: Use ViewModel for animation time
        self._view_model.tick(dt)
        self.update()

    # --- Interaction -----------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if self._mouse_handler.handle_press(e, self.frameGeometry()):
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._mouse_handler.handle_move(e):
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        handled, _was_click = self._mouse_handler.handle_release(e)
        if handled:
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def leaveEvent(self, e: QtCore.QEvent):
        self._mouse_handler.handle_leave()
        super().leaveEvent(e)

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        self._mark_user_activity()
        super().keyPressEvent(e)

    def _mark_user_activity(self):
        self._last_user_activity = time.monotonic()

    def _update_bubble_side_from_offset(self):
        """Update bubble side based on offset (called by BubbleController)."""
        self._view_model.set_bubble_side("center")

    def _available_screen_geometry(self) -> QtCore.QRect:
        """Get available screen geometry. Delegates to WindowLayoutManager."""
        return WindowLayoutManager.get_available_screen_geometry(self)

    def _clamp_window_position(self, desired: QtCore.QPoint) -> QtCore.QPoint:
        """Clamp window position to screen bounds. Delegates to WindowLayoutManager."""
        window_size = self.frameGeometry().size()
        screen_rect = self._available_screen_geometry()
        return WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

    def _move_window_to(self, point: QtCore.QPoint):
        """Move window to position. Delegates to WindowLayoutManager."""
        WindowLayoutManager.move_window_safely(self, point)

    def _compute_panel_size_hint(self) -> tuple[float, float]:
        """Compute panel size hint. Delegates to WindowLayoutManager."""
        return WindowLayoutManager.compute_panel_size_hint(
            self._view_model.sprite_size,
            self._bubble_text or "",
        )

    def _apply_window_preferred_size(self):
        """Apply preferred window size. Delegates to WindowLayoutManager."""
        panel_w_hint, panel_h_hint = self._compute_panel_size_hint()
        self._panel_width_hint = panel_w_hint
        self._panel_height_hint = panel_h_hint

        self._sizing_in_progress = True
        try:
            WindowLayoutManager.apply_window_preferred_size(
                self,
                self._view_model.sprite_size,
                panel_w_hint,
                panel_h_hint,
            )
        finally:
            self._sizing_in_progress = False

    def _update_sprite_size_hint(self, movie: QtGui.QMovie | None):
        """Update sprite size from movie. Uses WindowLayoutManager to extract size."""
        sprite_size = WindowLayoutManager.extract_sprite_size_from_movie(movie)
        if sprite_size:
            self._view_model.set_sprite_size(sprite_size)
        else:
            self._view_model.set_sprite_size(QtCore.QSize(200, 200))
        self._apply_window_preferred_size()

    def contextMenuEvent(self, e: QtGui.QContextMenuEvent):
        self._mark_user_activity()
        menu = create_doro_menu(
            parent=self, avatar_position="top-center", gif_movie=self._gif_movie
        )
        build_context_menu_content(self, menu)
        menu.exec(e.globalPos())

    # --- Painting --------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Disable animations - no bob (floating) or scale (breathing) effects
        # NOTE: ViewModel can calculate these, but we keep animations disabled for now
        bob = 0.0
        scale = 1.0

        # Calculate sprite center using RenderingEngine
        sprite_center, new_anchor = self._rendering_engine.calculate_sprite_center(
            self.size(), self._sprite_anchor_top
        )
        if new_anchor is not None:
            self._sprite_anchor_top = new_anchor

        # Render sprite using RenderingEngine
        self._rendering_engine.render_sprite(p, self._gif_movie, sprite_center, bob, scale)

        # Render text panel using RenderingEngine
        panel_should_draw = (
            (self._view_model.bubble_visible or self._bubble_text_show_override)
            and self._view_model.bubble_alpha > 0
            and bool((self._bubble_text or "").strip())
        )
        if panel_should_draw:
            from ..constants import COLOR_ALPHA_MAX

            alpha = min(max(int(self._view_model.bubble_alpha), 0), COLOR_ALPHA_MAX)
            self._panel_rect_cache = self._rendering_engine.render_text_panel(
                p, self._bubble_text, alpha, sprite_center, self.size(), self._panel_height_hint
            )
        else:
            self._panel_rect_cache = None

        font = QtGui.QFont()
        font.setPointSize(10)
        font.setWeight(QtGui.QFont.Weight.Bold)
        p.setFont(font)

    # ═══════════════════════════════════════════════════════════
    # Public Movement API - Window Operations
    # ═══════════════════════════════════════════════════════════

    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint:
        """Clamp window position to stay on screen (public API)."""
        return self._clamp_window_position(pos)

    def current_position(self) -> QtCore.QPoint:
        """Get the current top-left position of the window (public API)."""
        return self.frameGeometry().topLeft()

    def move_window_to(self, pos: QtCore.QPoint):
        """Move window to position (public API)."""
        self._move_window_to(pos)

    def resolve_move_state(
        self, key: str | None
    ) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        """Resolve movement state configuration (public API)."""
        return self._resolve_move_state(key)

    def get_bubble_offset(self) -> QtCore.QPointF:
        """Get the current bubble offset (public API for movement)."""
        return QtCore.QPointF(self._bubble_offset)

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False):
        """Apply bubble offset via BubbleController (public API)."""
        if self._bubble_controller:
            self._bubble_controller.apply_offset(offset, persist=persist)

    def reset_tick_timer(self, value: float):
        """Reset the tick timer used for movement animation (public API)."""
        self._last_tick_time = value

    # ═══════════════════════════════════════════════════════════
    # Event Callbacks from StateService and TransitionPlayer
    # ═══════════════════════════════════════════════════════════

    def _on_transition_movie_loaded(self, movie: QtGui.QMovie, sprite_size: QtCore.QSize):
        """
        Handle transition movie loaded signal from TransitionPlayer.

        Args:
            movie: The transition QMovie
            sprite_size: The sprite size from the transition GIF
        """
        # Set movie to window's GIF movie (temporarily for transition)
        self._gif_movie = movie
        # Update sprite size from transition GIF
        self._view_model.set_sprite_size(sprite_size)
        self._apply_window_preferred_size()
        self.update()

    def _on_transition_completed(self, target_state_key: str):
        """
        Handle transition completion signal from TransitionPlayer.

        Args:
            target_state_key: The target state key to load after transition
        """
        logger.debug(f"Transition completed, loading target state: {target_state_key}")
        # Load target state GIF using helper
        self._load_state_gif(target_state_key)

    # ═══════════════════════════════════════════════════════════
    # Event Callbacks from BubbleController
    # ═══════════════════════════════════════════════════════════

    def _on_bubble_text_changed(self, text: str, show_override: bool):
        """
        Handle bubble text change signal from BubbleController.

        Args:
            text: The new bubble text
            show_override: Whether to show bubble even if visibility is disabled
        """
        self._bubble_text = text
        self._bubble_text_show_override = show_override
        self.update()

    def _on_bubble_visibility_changed(self, visible: bool):
        """
        Handle bubble visibility change signal from BubbleController.

        Args:
            visible: Whether bubble should be visible
        """
        self._bubble_visible = visible
        self.update()

    def _on_bubble_offset_changed(self, offset: QtCore.QPointF):
        """
        Handle bubble offset change signal from BubbleController.

        Args:
            offset: The new bubble offset
        """
        self._bubble_offset = QtCore.QPointF(offset)
        self._update_bubble_side_from_offset()
        self.update()

    def _on_bubble_scale_changed(self, scale: float):
        """
        Handle bubble scale change signal from BubbleController.

        Args:
            scale: The new bubble scale
        """
        self._bubble_scale = scale
        self.update()

    # ═══════════════════════════════════════════════════════════
    # Movement State Resolution
    # ═══════════════════════════════════════════════════════════

    def _resolve_move_state(
        self, key: str | None
    ) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        """Resolve movement state configuration."""
        if not key:
            return None, None

        normalized = key.strip().lower()
        move_state = self._state_service.get_move_state(normalized)

        if not move_state:
            return None, None

        # Convert MoveState to MoveStateSettings for compatibility
        settings = MoveStateSettings(
            state_key=move_state.state_key,
            direction=move_state.direction,
            default_distance=move_state.default_distance,
            default_speed=move_state.default_speed,
        )

        return normalized, settings

    def _set_busy_cursor(self, enabled: bool):
        if enabled and not self._chat_cursor_overridden:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
            self._chat_cursor_overridden = True
        elif not enabled and self._chat_cursor_overridden:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._chat_cursor_overridden = False

    def _toggle_bubble(self, checked: bool):
        # Update through StateService
        if not self._current_state_key:
            return
        # Update state via StateService
        if self._state_service.update_visual_config(
            self._current_state_key, bubble_visible=checked
        ):
            # ViewModel will be updated by state change event
            self._bubble_controller.set_visible(checked)

    # NOTE: _on_bubble_text_requested() and _on_chat_notification() removed
    # These signals are now handled through CoreManager in DoroApp

    def _set_bubble_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        self._bubble_controller.set_text(
            text,
            override_visibility=override_visibility,
            auto_hide=auto_hide,
            hide_delay_ms=hide_delay_ms,
        )
        self._apply_window_preferred_size()

    def _clear_bubble_text(self):
        self._bubble_controller.clear_text()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._set_busy_cursor(False)

        # Clean up resources
        try:
            # Clear all GIF resources using GifPlayer
            self._gif_player.clear()
            self._gif_movie = None

            if self._timer:
                try:
                    self._timer.stop()
                except Exception:
                    pass

            # Save configuration on close
            if self._config_manager:
                self._config_manager.save()
            elif self._config:
                self._config.sync()
        except Exception:
            pass

        super().closeEvent(event)
