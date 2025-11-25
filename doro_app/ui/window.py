"""Main application window and UI logic for Doro."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    TIMER_INTERVAL_MS, BUBBLE_AUTO_HIDE_MS, WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, SPRITE_DEFAULT_WIDTH, SPRITE_DEFAULT_HEIGHT,
    SPRITE_OFFSET_X, PANEL_DEFAULT_WIDTH_HINT, PANEL_DEFAULT_HEIGHT_HINT,
    BUBBLE_DEFAULT_OFFSET_X, BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE, MOVEMENT_ONLY_STATE_KEYS,
    DEFAULT_MOVE_STATE_KEY, CLICK_DRAG_THRESHOLD_PX, SPRITE_MIN_SIZE, SPRITE_MARGIN_X,
    SPRITE_MARGIN_BOTTOM, SPRITE_BOB_ALLOWANCE, SPRITE_PANEL_RESERVE_OFFSET,
    get_default_fill_colors, get_default_blush_color, get_default_eye_color,
)
from .components.bubble_controller import BubbleConfig, BubbleController
from .components.gif_player import GifPlayer
from .rendering.design_tokens import tokens
from .rendering.fallback_sprite import draw_fallback_sprite
from .rendering.rendering_engine import RenderingEngine
from .layout.layout_manager import WindowLayoutManager
from .viewmodels.doro_viewmodel import DoroViewModel
from ..core.chat.controller import ChatController
from ..core.chat.orchestrator import ChatOrchestrator
from ..utils.logger import get_logger
from ..core.movement.manager import MovementManager
from ..utils.models import MoveStateSettings
from ..core.state import State, StateChangeEvent
from ..core.state import StateService
from ..core.state.transition_player import TransitionPlayer
from .theme.theme import ensure_application_theme
from .theme.themed_menu import build_context_menu_content, create_doro_menu
from .helpers import ChatUIHelper
from ..utils.utils import safe_float as _safe_float, safe_int as _safe_int

logger = get_logger(__name__)


class DoroWindow(QtWidgets.QWidget):
    def __init__(
        self,
        state_service: StateService,
        config: QtCore.QSettings,
        not_topmost: bool = False,
    ):
        """
        Initialize the Doro window (UI layer only).

        Args:
            state_service: State management service (injected)
            config: QSettings for configuration (injected)
            not_topmost: If True, window will not stay on top

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
        self._config = config

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
        self._transition_player: TransitionPlayer | None = None
        self._bubble_controller: BubbleController | None = None
        self._movement: MovementManager | None = None
        # Chat
        self._chat_controller: ChatController | None = None
        self._chat_orchestrator: ChatOrchestrator | None = None

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
        self._state_list_text: str = ""
        self._movement_only_state_keys: set[str] = MOVEMENT_ONLY_STATE_KEYS
        self._move_state_list_text: str = ""

        self._gif_player = GifPlayer()
        self._gif_movie: QtGui.QMovie | None = None

        self._bubble_text = ""
        self._bubble_text_show_override = False
        self._bubble_auto_hide_ms = BUBBLE_AUTO_HIDE_MS
        self._bubble_dragging = False
        self._bubble_resizing = False
        self._bubble_drag_start: QtCore.QPointF | None = None
        self._bubble_initial_offset = QtCore.QPointF(0.0, 0.0)
        self._bubble_resize_start: QtCore.QPointF | None = None
        self._bubble_resize_anchor: QtCore.QPointF | None = None
        self._bubble_initial_scale = 1.0
        self._bubble_resize_cursor_active = False
        self._last_user_activity = time.monotonic()

        self._panel_width_hint = PANEL_DEFAULT_WIDTH_HINT
        self._panel_height_hint = PANEL_DEFAULT_HEIGHT_HINT
        self._panel_rect_cache: QtCore.QRectF | None = None
        self._sprite_anchor_top: float | None = None

        self._default_move_state_key = DEFAULT_MOVE_STATE_KEY
        self._sizing_in_progress = False
        self._last_tick_time = time.monotonic()

        self._click_press_pos: QtCore.QPointF | None = None
        self._click_was_dragging = False
        self._drag_pos: QtCore.QPoint | None = None

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
            self.move(g.right() - self.width() - 40, g.bottom() - self.height() - 120)

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
        transition_player: TransitionPlayer,
        bubble_controller: BubbleController,
        movement_manager: MovementManager,
        chat_controller: ChatController,
        chat_orchestrator: ChatOrchestrator,
    ):
        """
        Wire dependencies after window construction.

        This two-phase initialization is necessary due to circular dependencies:
        - Managers need window reference (for update(), move(), etc.)
        - Window needs managers for event handling

        In Phase 3, this will be refactored to use Qt Signals instead.

        Args:
            state_controller: Coordinates state changes with ViewModel
            gif_controller: Handles GIF loading and playback
            dialog_manager: Manages dialog windows
            click_action_controller: Handles click actions
            transition_player: Handles state transition animations
            bubble_controller: Manages bubble UI state
            movement_manager: Handles window movement
            chat_controller: Handles chat interactions
            chat_orchestrator: Coordinates chat and movement
        """
        # Wire controllers
        self._state_controller = state_controller
        self._gif_controller = gif_controller
        self._dialog_manager = dialog_manager
        self._click_action_controller = click_action_controller

        # Wire managers
        self._transition_player = transition_player
        self._bubble_controller = bubble_controller
        self._movement = movement_manager

        # Wire chat components
        self._chat_controller = chat_controller
        self._chat_orchestrator = chat_orchestrator

        # ─────────────────────────────────────────────────────────
        # Connect controller signals
        # ─────────────────────────────────────────────────────────
        self._state_controller.repaint_requested.connect(self.update)
        self._state_controller.state_changed.connect(self._on_controller_state_changed)
        self._state_controller.state_list_updated.connect(self._on_state_list_updated)

        self._gif_controller.repaint_requested.connect(self.update)
        self._gif_controller.gif_loaded.connect(self._on_gif_loaded)
        self._gif_controller.sprite_size_changed.connect(self._on_sprite_size_changed)

        # ─────────────────────────────────────────────────────────
        # Connect manager signals
        # ─────────────────────────────────────────────────────────
        self._transition_player.transition_movie_loaded.connect(self._on_transition_movie_loaded)
        self._transition_player.transition_completed.connect(self._on_transition_completed)

        self._chat_orchestrator.bubble_text_requested.connect(self._on_bubble_text_requested)
        self._chat_orchestrator.bubble_clear_requested.connect(self._clear_bubble_text)
        self._chat_orchestrator.busy_cursor_requested.connect(self._set_busy_cursor)

        # ─────────────────────────────────────────────────────────
        # Apply configuration
        # ─────────────────────────────────────────────────────────
        offset_x = _safe_float(self._config.value("ui/bubble_offset_x", BUBBLE_DEFAULT_OFFSET_X), BUBBLE_DEFAULT_OFFSET_X)
        offset_y = _safe_float(self._config.value("ui/bubble_offset_y", BUBBLE_DEFAULT_OFFSET_Y), BUBBLE_DEFAULT_OFFSET_Y)
        scale_pref = _safe_float(self._config.value("ui/bubble_scale", BUBBLE_DEFAULT_SCALE), BUBBLE_DEFAULT_SCALE)
        self._bubble_controller.apply_persisted_config(
            BubbleConfig(offset_x=offset_x, offset_y=offset_y, scale=scale_pref, auto_hide_ms=self._bubble_auto_hide_ms)
        )

    # ─────────────────────────────────────────────────────────
    # Controller signal handlers
    # ─────────────────────────────────────────────────────────

    def _on_controller_state_changed(self, state_key: str):
        """
        Handle state change from StateController.

        StateController handles ViewModel updates, we just need to load the GIF.
        """
        self._current_state_key = state_key

        # Check if transition should play
        # (TransitionPlayer will handle loading the target GIF after transition)
        # For now, just load the GIF directly if no transition
        gif_resource_id = self._state_service.get_gif_id(state_key)
        if gif_resource_id:
            gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
            if gif_path:
                self._gif_controller.load_gif(str(gif_path))

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
        self._movement.process_active_movement(dt)

        # NEW: Use ViewModel for animation time
        self._view_model.tick(dt)
        self.update()

    # --- Interaction -----------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._bubble_controller.begin_transform(e.position()):
                self._bubble_controller.update_cursor(e.position())
                e.accept()
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._click_press_pos = e.position()
            self._click_was_dragging = False
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if e.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._mark_user_activity()
        if self._bubble_controller.update_transform(e.position()):
            self._bubble_controller.update_cursor(e.position())
            e.accept()
            return
        if not self._bubble_dragging and not self._bubble_resizing:
            self._bubble_controller.update_cursor(e.position())
        if self._drag_pos is not None and e.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if (
                self._click_press_pos is not None
                and not self._click_was_dragging
                and (e.position() - self._click_press_pos).manhattanLength() > CLICK_DRAG_THRESHOLD_PX
            ):
                self._click_was_dragging = True
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._bubble_controller.end_transform():
                self._bubble_controller.update_cursor(e.position())
                e.accept()
                return
            was_click = (
                not self._click_was_dragging
                and self._click_press_pos is not None
                and (e.position() - self._click_press_pos).manhattanLength() <= CLICK_DRAG_THRESHOLD_PX
            )
            self._drag_pos = None
            self._click_press_pos = None
            self._click_was_dragging = False
            super().mouseReleaseEvent(e)
            if was_click:
                self._trigger_click_action()
            return
        self._drag_pos = None
        self._click_press_pos = None
        self._click_was_dragging = False
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e: QtCore.QEvent):
        self._bubble_controller.update_cursor(None)
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
        if not isinstance(point, QtCore.QPoint):
            return
        current = self.frameGeometry().topLeft()
        if current == point:
            return
        handle = self.windowHandle()
        if handle is not None:
            try:
                handle.setPosition(point)
            except Exception:
                pass
        self.move(point)
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        try:
            self.raise_()
        except Exception:
            pass

    def _compute_panel_size_hint(self) -> tuple[float, float]:
        """Compute panel size hint. Delegates to WindowLayoutManager."""
        return WindowLayoutManager.compute_panel_size_hint(
            self._view_model.sprite_size,
            self._bubble_text or "",
        )

    def _apply_window_preferred_size(self):
        sprite_w = max(120.0, float(self._view_model.sprite_size.width()))
        sprite_h = max(120.0, float(self._view_model.sprite_size.height()))
        panel_w_hint, panel_h_hint = self._compute_panel_size_hint()
        self._panel_width_hint = panel_w_hint
        self._panel_height_hint = panel_h_hint

        desired_w = max(
            380,
            int(round(max(sprite_w + 120.0, panel_w_hint + 48.0))),
        )
        desired_h = max(
            320,
            int(round(sprite_h + panel_h_hint + 120.0)),
        )
        current_size = self.size()
        min_size = self.minimumSize()
        min_changed = (
            min_size.width() != desired_w or min_size.height() != desired_h
        )
        needs_resize = (
            current_size.width() < desired_w or current_size.height() < desired_h
        )

        if min_changed or needs_resize:
            self._sizing_in_progress = True
            try:
                if min_changed:
                    self.setMinimumSize(desired_w, desired_h)
                if needs_resize:
                    self.resize(
                        max(current_size.width(), desired_w),
                        max(current_size.height(), desired_h),
                    )
            finally:
                self._sizing_in_progress = False
        self.update()

    def _update_sprite_size_hint(self, movie: QtGui.QMovie | None):
        if movie and movie.isValid():
            rect = movie.frameRect()
            if rect.width() > 0 and rect.height() > 0:
                self._view_model.set_sprite_size(rect.size())
                self._apply_window_preferred_size()
                return
        self._view_model.set_sprite_size(QtCore.QSize(200, 200))
        self._apply_window_preferred_size()

    def contextMenuEvent(self, e: QtGui.QContextMenuEvent):
        self._mark_user_activity()
        menu = create_doro_menu(
            parent=self,
            avatar_position="top-center",
            gif_movie=self._gif_movie
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
            self.size(),
            self._sprite_anchor_top
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
            alpha = min(max(int(self._view_model.bubble_alpha), 0), 255)
            self._panel_rect_cache = self._rendering_engine.render_text_panel(
                p,
                self._bubble_text,
                alpha,
                sprite_center,
                self.size(),
                self._panel_height_hint
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

    def move_window_to(self, pos: QtCore.QPoint):
        """Move window to position (public API)."""
        self._move_window_to(pos)

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
        # Load target state GIF
        gif_resource_id = self._state_service.get_gif_id(target_state_key)
        if gif_resource_id:
            gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
            if gif_path:
                self._load_gif(str(gif_path))

    def _is_movement_only_state(self, key: str) -> bool:
        """Check if state is movement-only (delegates to StateController)."""
        return self._state_controller.is_movement_only_state(key)

    def _visible_state_keys(self) -> list[str]:
        """Get visible state keys (delegates to StateController)."""
        return self._state_controller.visible_state_keys()

    def _resolve_move_state(self, key: str | None) -> tuple[Optional[str], Optional[MoveStateSettings]]:
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

    def _apply_state_settings(self):
        """Apply state settings (delegates to StateController)."""
        self._state_controller.apply_state_settings(self._current_state_key)

    def _load_gif(self, path: str | None):
        """Load GIF (delegates to GifController)."""
        self._gif_controller.load_gif(path)

    def _set_state(self, key: str):
        """Set state (delegates to StateController)."""
        self._state_controller.set_state(key)

    def _set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        """Set state GIF (delegates to StateController)."""
        return self._state_controller.set_state_gif(key, Path(source_path))

    def _show_state_manager(self):
        """Show state manager dialog (delegates to DialogManager)."""
        self._dialog_manager.show_state_manager()

    def _show_move_gif_manager(self):
        """Show move state manager dialog (delegates to DialogManager)."""
        self._dialog_manager.show_move_state_manager()

    def _clear_state_gif(self):
        """Clear state GIF (delegates to StateController)."""
        self._state_controller.clear_state_gif(self._current_state_key)

    def _trigger_click_action(self):
        """Trigger random click action (delegates to ClickActionController)."""
        self._mark_user_activity()
        self._click_action_controller.trigger_random_action()

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
            self._current_state_key,
            bubble_visible=checked
        ):
            # ViewModel will be updated by state change event
            self._bubble_controller.set_visible(checked)

    def _rename_pet(self):
        """Rename pet (delegates to DialogManager)."""
        if self._current_state_key:
            if self._dialog_manager.show_rename_dialog(self._current_state_key):
                self.update()

    def _add_state(self, checked: bool = False) -> str | None:
        """Add state (delegates to DialogManager)."""
        return self._dialog_manager.show_add_state_dialog()

    def _remove_state_by_key(
        self,
        key: str,
        *,
        confirm: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        """Remove state by key (delegates to DialogManager)."""
        if confirm:
            return self._dialog_manager.show_remove_state_confirmation(key)
        else:
            return self._state_service.remove_state(key)

    def _remove_current_state(self):
        """Remove current state (delegates to DialogManager)."""
        if self._current_state_key:
            self._dialog_manager.show_remove_state_confirmation(self._current_state_key)

    def _on_bubble_text_requested(self, text: str, kwargs: dict):
        """
        Handle bubble text request from ChatOrchestrator signal.

        Args:
            text: Text to display in bubble
            kwargs: Additional arguments for _set_bubble_text() (dict)
        """
        self._set_bubble_text(text, **kwargs)

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

            if self._config:
                self._config.sync()
        except Exception:
            pass

        super().closeEvent(event)
