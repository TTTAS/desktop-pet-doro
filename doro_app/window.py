"""Main application window and UI logic for Doro."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .constants import (
    TIMER_INTERVAL_MS, BUBBLE_AUTO_HIDE_MS, WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, SPRITE_DEFAULT_WIDTH, SPRITE_DEFAULT_HEIGHT,
    SPRITE_OFFSET_X, PANEL_DEFAULT_WIDTH_HINT, PANEL_DEFAULT_HEIGHT_HINT,
    MOVEMENT_STEP_PX, BUBBLE_DEFAULT_OFFSET_X, BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE, BUBBLE_DEFAULT_ALPHA, MOVEMENT_ONLY_STATE_KEYS,
    DEFAULT_MOVE_STATE_KEY, CLICK_DRAG_THRESHOLD_PX, SPRITE_MIN_SIZE, SPRITE_MARGIN_X,
    SPRITE_MARGIN_BOTTOM, SPRITE_BOB_ALLOWANCE, SPRITE_PANEL_RESERVE_OFFSET,
    # Fallback sprite geometry
    FACE_CENTER_X, FACE_CENTER_Y_TOP, FACE_CENTER_Y_BOTTOM, FACE_LEFT_X, FACE_RIGHT_X,
    FACE_CONTROL_X_LEFT, FACE_CONTROL_X_RIGHT,
    BLUSH_LEFT_X, BLUSH_RIGHT_X, BLUSH_Y, BLUSH_WIDTH, BLUSH_HEIGHT,
    EYE_LEFT_X, EYE_RIGHT_X, EYE_Y, EYE_WIDTH, EYE_HEIGHT,
    MOUTH_START_X, MOUTH_START_Y, MOUTH_CONTROL1_X, MOUTH_CONTROL1_Y,
    MOUTH_CONTROL2_X, MOUTH_CONTROL2_Y, MOUTH_END_X, MOUTH_END_Y, MOUTH_PEN_WIDTH,
    DEFAULT_BORDER_COLOR, DEFAULT_BORDER_WIDTH,
    get_default_fill_colors, get_default_blush_color, get_default_eye_color,
)
from .ui.components.bubble_controller import BubbleConfig, BubbleController
from .ui.components.gif_player import GifPlayer
from .ui.design_tokens import tokens
from .ui.fallback_sprite import draw_fallback_sprite
from .ui.view_model import DoroViewModel
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .utils.logger import get_logger
from .core.movement.manager import MovementManager
from .utils.models import MoveStateSettings
from .utils.paths import ACTION_TRANSITION_DIR, CLICK_ACTIONS_PATH, MOVE_DIR, PROMPT_PATH, STATE_DIR
from .core.state import State, StateChangeEvent
from .core.state import GifRepository, MoveStateRepository, StateRepository, TransitionStateRepository
from .core.state import StateService
from .core.state.transition_player import TransitionPlayer
from .ui.theme.theme import ensure_application_theme
from .ui.theme.themed_menu import build_context_menu_content, create_doro_menu
from .ui.helpers import ChatUIHelper
from .utils.utils import safe_float as _safe_float, safe_int as _safe_int

logger = get_logger(__name__)


class DoroWindow(QtWidgets.QWidget):
    def __init__(self, not_topmost: bool = False):
        super().__init__()
        logger.info("Initializing Doro window")
        ensure_application_theme()
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

        # NEW: Presentation state managed by ViewModel
        self._view_model = DoroViewModel()

        # Animation clock
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TIMER_INTERVAL_MS)

        # Appearance/animation parameters
        # OLD state data removed - now managed by StateService
        self._current_state_key: str = ""
        self._state_list_text: str = ""
        self._movement_only_state_keys: set[str] = MOVEMENT_ONLY_STATE_KEYS
        self._move_state_list_text: str = ""
        # NOTE: Legacy variables kept for gradual migration
        # Animation state now primarily in _view_model
        self._amplitude = 0.0
        self._scale_amp = 0.0
        self._fill_colors: tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor] = get_default_fill_colors()
        self._cheek_alpha = 0.0
        self._blush_base = get_default_blush_color()
        self._eye_color = get_default_eye_color()
        self._bubble_visible = True
        self._bubble_alpha = BUBBLE_DEFAULT_ALPHA
        self._bubble_side = "center"
        self._name_tag = "doro"
        self._gif_player = GifPlayer()
        self._gif_movie: QtGui.QMovie | None = None  # Current movie from player
        self._bubble_text = ""
        self._bubble_text_show_override = False
        self._bubble_auto_hide_ms = BUBBLE_AUTO_HIDE_MS
        self._bubble_offset = QtCore.QPointF(0.0, 0.0)
        self._bubble_scale = 1.0
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
        self._sprite_size = QtCore.QSize(SPRITE_DEFAULT_WIDTH, SPRITE_DEFAULT_HEIGHT)
        self._sprite_offset_x = SPRITE_OFFSET_X
        self._sprite_anchor_top: float | None = None
        self._movement_step_px = MOVEMENT_STEP_PX
        self._default_move_state_key = DEFAULT_MOVE_STATE_KEY
        # Removed: self._move_state_defs - now using StateService.all_move_state_keys()

        # NEW architecture - state management without Window coupling
        # Repositories are created and injected into StateService
        # Window does NOT retain direct references to repositories
        gif_repo = GifRepository(STATE_DIR)
        state_repo = StateRepository(STATE_DIR / "states.json")
        move_repo = MoveStateRepository(STATE_DIR / "move_states.json")
        transition_repo = TransitionStateRepository(ACTION_TRANSITION_DIR / "transitions.json")
        self._state_service = StateService(
            state_repo,
            move_repo,
            gif_repo,
            STATE_DIR / "state_list.txt",
            transition_repo,
        )

        # Connect state change events
        self._state_service.on_state_changed = self._on_state_changed
        self._state_service.on_states_modified = self._on_states_modified

        # Create transition player for state change animations
        self._transition_player = TransitionPlayer(self, self._state_service)

        self._bubble_controller = BubbleController(self)
        self._movement = MovementManager(self, self._state_service, MOVEMENT_STEP_PX)
        self._sizing_in_progress = False
        self._last_tick_time = time.monotonic()

        self._state_storage_dir = STATE_DIR
        self._state_storage_dir.mkdir(parents=True, exist_ok=True)
        self._move_storage_dir = MOVE_DIR
        self._move_storage_dir.mkdir(parents=True, exist_ok=True)
        self._transition_action_dir = ACTION_TRANSITION_DIR
        self._transition_action_dir.mkdir(parents=True, exist_ok=True)
        self._default_idle_gif = self._state_storage_dir / "idle.gif"
        self._state_list_path = self._state_storage_dir / "state_list.txt"
        self._move_state_list_path = self._state_storage_dir / "move_state_list.txt"
        self._state_config_path = self._state_storage_dir / "states.json"
        self._prompt_file_path = PROMPT_PATH
        self._click_actions_path = CLICK_ACTIONS_PATH
        self._click_press_pos: QtCore.QPointF | None = None
        self._click_was_dragging = False

        # QSettings must be created before reading/writing
        self._config = QtCore.QSettings("doro-pet", "doro")

        # Write default idle.gif once (if user hasn't set any)
        if not self._config.contains("state/idle/gif_path") and self._default_idle_gif.is_file():
            self._config.setValue("state/idle/gif_path", str(self._default_idle_gif))

        offset_x = _safe_float(self._config.value("ui/bubble_offset_x", BUBBLE_DEFAULT_OFFSET_X), BUBBLE_DEFAULT_OFFSET_X)
        offset_y = _safe_float(self._config.value("ui/bubble_offset_y", BUBBLE_DEFAULT_OFFSET_Y), BUBBLE_DEFAULT_OFFSET_Y)
        scale_pref = _safe_float(self._config.value("ui/bubble_scale", BUBBLE_DEFAULT_SCALE), BUBBLE_DEFAULT_SCALE)
        self._bubble_controller.apply_persisted_config(
            BubbleConfig(offset_x=offset_x, offset_y=offset_y, scale=scale_pref, auto_hide_ms=self._bubble_auto_hide_ms)
        )
        self._apply_window_preferred_size()

        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=lambda: self._state_list_text or "",
            movement_hint_provider=lambda: self._movement.instruction_text(),
            parent=self,
        )
        self._chat_orchestrator = ChatOrchestrator(self._chat_controller, self._movement, self._state_service)

        # Connect ChatOrchestrator signals to Window methods
        self._chat_orchestrator.bubble_text_requested.connect(self._on_bubble_text_requested)
        self._chat_orchestrator.bubble_clear_requested.connect(self._clear_bubble_text)
        self._chat_orchestrator.busy_cursor_requested.connect(self._set_busy_cursor)

        self._chat_ui = ChatUIHelper(self)
        self._chat_cursor_overridden = False

        # Initialize state system (NEW architecture)
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        # Restore last state from QSettings
        saved_state_key = self._config.value("current_state", "idle")
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

        # Drag move support
        self._drag_pos: QtCore.QPoint | None = None

        # Context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        # Place near bottom-right of primary screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(g.right() - self.width() - 40, g.bottom() - self.height() - 120)

        self.setWindowTitle("doro")

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

    def _sprite_center(self) -> QtCore.QPointF:
        base_x = self.width() / 2.0 + getattr(self, "_sprite_offset_x", 0.0)
        half_w = max(SPRITE_MIN_SIZE, self._sprite_size.width() / 2.0)
        half_h = max(SPRITE_MIN_SIZE, self._sprite_size.height() / 2.0)
        margin_x = SPRITE_MARGIN_X
        min_center_x = half_w + margin_x
        max_center_x = self.width() - half_w - margin_x
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))
        bob_allowance = abs(getattr(self, "_amplitude", 0.0)) + SPRITE_BOB_ALLOWANCE
        margin_bottom = SPRITE_MARGIN_BOTTOM
        min_center_y = half_h + bob_allowance
        max_center_y = self.height() - half_h - margin_bottom
        if max_center_y < min_center_y:
            max_center_y = min_center_y
        if getattr(self, "_sprite_anchor_top", None) is None:
            panel_reserve = getattr(self, "_panel_height_hint", PANEL_DEFAULT_HEIGHT_HINT) + SPRITE_PANEL_RESERVE_OFFSET
            initial_base_y = (self.height() - panel_reserve) / 2.0
            initial_base_y = max(min_center_y, min(max_center_y, initial_base_y))
            self._sprite_anchor_top = max(0.0, initial_base_y - half_h)
        anchor_top = max(0.0, float(self._sprite_anchor_top or 0.0))
        base_y = anchor_top + half_h
        clamped_base_y = max(min_center_y, min(max_center_y, base_y))
        if clamped_base_y != base_y:
            anchor_top = max(0.0, clamped_base_y - half_h)
            self._sprite_anchor_top = anchor_top
            base_y = anchor_top + half_h
        return QtCore.QPointF(base_x, base_y)

    def _mark_user_activity(self):
        self._last_user_activity = time.monotonic()

    def _update_bubble_side_from_offset(self):
        """Update bubble side based on offset (called by BubbleController)."""
        self._bubble_side = "center"

    def _available_screen_geometry(self) -> QtCore.QRect:
        handle = self.windowHandle()
        screen = handle.screen() if handle else None
        if not screen:
            screen = QtWidgets.QApplication.primaryScreen()
        return screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1920, 1080)

    def _clamp_window_position(self, desired: QtCore.QPoint) -> QtCore.QPoint:
        geo = self.frameGeometry()
        rect = self._available_screen_geometry()
        max_x = rect.left() + max(0, rect.width() - geo.width())
        max_y = rect.top() + max(0, rect.height() - geo.height())
        min_x = rect.left()
        min_y = rect.top()
        clamped_x = max(min_x, min(max_x, desired.x()))
        clamped_y = max(min_y, min(max_y, desired.y()))
        return QtCore.QPoint(clamped_x, clamped_y)

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
        text = (self._bubble_text or "").strip()
        sprite_w = max(120.0, float(self._sprite_size.width()))
        panel_width = max(160.0, sprite_w)
        available_text_width = max(80.0, panel_width - 56.0)

        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.Bold)
        metrics = QtGui.QFontMetrics(font)

        if text:
            flags = int(
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignTop
            )
            flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
            text_rect = metrics.boundingRect(
                QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
                flags,
                text,
            )
            text_height = float(text_rect.height())
        else:
            text_height = float(metrics.lineSpacing())

        panel_height = max(80.0, text_height + 56.0)
        return panel_width, panel_height

    def _apply_window_preferred_size(self):
        sprite_w = max(120.0, float(self._sprite_size.width()))
        sprite_h = max(120.0, float(self._sprite_size.height()))
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
                self._sprite_size = rect.size()
                self._apply_window_preferred_size()
                return
        self._sprite_size = QtCore.QSize(200, 200)
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

        # NEW: Use ViewModel for animation calculations
        bob = self._view_model.calculate_bob()
        scale = self._view_model.calculate_scale()

        sprite_center = self._sprite_center()
        p.save()
        p.translate(sprite_center.x(), sprite_center.y() + bob)
        p.scale(scale, scale)

        if self._gif_movie and not self._gif_movie.currentPixmap().isNull():
            pixmap = self._gif_movie.currentPixmap()
            p.translate(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            p.drawPixmap(0, 0, pixmap)
        else:
            # Draw fallback sprite when no GIF is available (use ViewModel colors)
            draw_fallback_sprite(
                p,
                self._view_model.fill_colors,
                self._view_model.cheek_alpha,
                self._view_model.blush_color,
                self._view_model.eye_color
            )

        p.restore()

        panel_should_draw = (
            (self._bubble_visible or self._bubble_text_show_override)
            and self._bubble_alpha > 0
            and bool((self._bubble_text or "").strip())
        )
        if panel_should_draw:
            alpha = min(max(int(self._bubble_alpha), 0), 255)
            self._draw_text_panel(p, alpha)
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
    # Event Callbacks from StateService
    # ═══════════════════════════════════════════════════════════

    # NEW: Event callbacks from StateService
    def _on_state_changed(self, event: StateChangeEvent) -> None:
        """Handle state change events from StateService."""
        state = event.new_state

        # Update current state tracking (for compatibility with old code)
        self._current_state_key = event.new_key
        self._state_list_text = self._state_service.write_state_list()

        # Try to play transition animation
        # If transition exists and plays, it will load the target state GIF when complete
        if self._transition_player.play_transition(event.old_key, event.new_key):
            logger.debug(f"Transition animation started: {event.old_key} -> {event.new_key}")
            # Visual config will be applied when transition completes
            # For now, just update the visual parameters (transition GIF is playing)
            # The target state GIF will be loaded by TransitionPlayer after transition completes
        else:
            # No transition available - load target state GIF directly
            gif_resource_id = self._state_service.get_gif_id(event.new_key)
            if gif_resource_id:
                gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
                if gif_path:
                    self._load_gif(str(gif_path))

        # Apply visual config (even during transitions, for when it completes)
        visual = state.visual

        # NEW: Apply visual config to ViewModel
        self._view_model.set_bob_amplitude(visual.bob_amplitude)
        self._view_model.set_scale_amplitude(visual.scale_amplitude)
        self._view_model.set_fill_colors(
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._view_model.set_cheek_alpha(visual.cheeks_alpha)
        self._view_model.set_blush_color(QtGui.QColor(visual.blush_color))
        self._view_model.set_eye_color(QtGui.QColor(visual.eye_color))
        self._view_model.set_bubble_visible(visual.bubble_visible)
        self._view_model.set_bubble_alpha(visual.bubble_alpha)
        self._view_model.set_name_tag(state.name_tag)

        # Keep legacy variables in sync (for gradual migration)
        self._amplitude = visual.bob_amplitude
        self._scale_amp = visual.scale_amplitude
        self._fill_colors = self._view_model.fill_colors
        self._cheek_alpha = visual.cheeks_alpha
        self._blush_base = self._view_model.blush_color
        self._eye_color = self._view_model.eye_color
        self._bubble_visible = visual.bubble_visible
        self._bubble_alpha = visual.bubble_alpha
        self._name_tag = state.name_tag

        # Persist to QSettings
        self._config.setValue("current_state", event.new_key)

        # Trigger repaint
        self.update()

    def _on_states_modified(self) -> None:
        """Handle state list modifications (add/remove states)."""
        self._state_list_text = self._state_service.write_state_list()

    def _is_movement_only_state(self, key: str) -> bool:
        # NEW: Use StateService
        return self._state_service.is_movement_only_state(key)

    def _visible_state_keys(self) -> list[str]:
        # NEW: Use StateService
        return self._state_service.visible_state_keys()

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
        """Apply current state settings from StateService."""
        if not self._current_state_key:
            return

        state = self._state_service.get_state(self._current_state_key)
        if not state:
            return

        # Apply visual config to ViewModel
        visual = state.visual
        self._view_model.set_bob_amplitude(visual.bob_amplitude)
        self._view_model.set_scale_amplitude(visual.scale_amplitude)
        self._view_model.set_fill_colors(
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._view_model.set_cheek_alpha(visual.cheeks_alpha)
        self._view_model.set_blush_color(QtGui.QColor(visual.blush_color))
        self._view_model.set_eye_color(QtGui.QColor(visual.eye_color))
        self._view_model.set_bubble_visible(visual.bubble_visible)
        self._view_model.set_bubble_alpha(visual.bubble_alpha)
        self._view_model.set_name_tag(state.name_tag)

        # Keep legacy variables in sync
        self._amplitude = visual.bob_amplitude
        self._scale_amp = visual.scale_amplitude
        self._fill_colors = self._view_model.fill_colors
        self._cheek_alpha = visual.cheeks_alpha
        self._blush_base = self._view_model.blush_color
        self._eye_color = self._view_model.eye_color
        self._bubble_visible = visual.bubble_visible
        self._bubble_alpha = visual.bubble_alpha
        self._name_tag = state.name_tag

        # Load GIF
        gif_resource_id = self._state_service.get_gif_id(self._current_state_key)
        if gif_resource_id:
            gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
            if gif_path:
                self._load_gif(str(gif_path))
                return

        # Fallback to default idle GIF
        if self._default_idle_gif.is_file():
            try:
                self._load_gif(str(self._default_idle_gif.resolve()))
            except OSError:
                self._load_gif(str(self._default_idle_gif))
        else:
            self._load_gif(None)

    def _load_gif(self, path: str | None):
        # Disconnect old movie if exists
        if self._gif_movie:
            try:
                self._gif_movie.frameChanged.disconnect(self._on_movie_frame_changed)
            except (RuntimeError, TypeError):
                pass

        # Clear all movies from player
        self._gif_player.clear()
        self._gif_movie = None

        if not path:
            self._update_sprite_size_hint(None)
            return

        path_obj = Path(path)
        if not path_obj.is_file():
            self._update_sprite_size_hint(None)
            return

        # Load using GifPlayer for unified resource management
        movie = self._gif_player.load(path_obj)
        if not movie:
            self._update_sprite_size_hint(None)
            return

        movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(self._on_movie_frame_changed)
        self._gif_movie = movie
        self._update_sprite_size_hint(movie)

    def _on_movie_frame_changed(self, _frame: int):
        if self._gif_movie:
            pixmap = self._gif_movie.currentPixmap()
            if not pixmap.isNull():
                frame_size = pixmap.size()
                if frame_size != self._sprite_size:
                    self._sprite_size = QtCore.QSize(frame_size)
                    self._apply_window_preferred_size()
        self.update()

    def _set_state(self, key: str):
        # NEW: Use StateService
        self._state_service.set_state(key)

    def _set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        # NEW: Use StateService
        return self._state_service.set_primary_gif(key, Path(source_path))

    def _show_state_manager(self):
        from .ui.dialogs.state import show_state_manager
        show_state_manager(self._state_service, parent=self)

    def _show_move_gif_manager(self):
        from .ui.dialogs.move_state import show_move_state_manager
        show_move_state_manager(self._state_service, parent=self)

    def _clear_state_gif(self):
        # Clear GIF for current state
        if self._current_state_key:
            state = self._state_service.get_state(self._current_state_key)
            if state and state.gif_id:
                self._state_service.delete_gif(state.gif_id)
                self._state_service.update_state(self._current_state_key, gif_id=None)

    def _load_click_actions(self) -> list[str]:
        path = getattr(self, "_click_actions_path", None)
        if not path:
            return []
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _trigger_click_action(self):
        self._mark_user_activity()
        actions = self._load_click_actions()
        if not actions or self._chat_orchestrator.is_inflight:
            return
        message = random.choice(actions).strip()
        if not message:
            return
        self._chat_orchestrator.send_message(message)

    def _set_busy_cursor(self, enabled: bool):
        if enabled and not self._chat_cursor_overridden:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
            self._chat_cursor_overridden = True
        elif not enabled and self._chat_cursor_overridden:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._chat_cursor_overridden = False

    def _toggle_bubble(self, checked: bool):
        # NEW: Update through StateService
        if not self._current_state_key:
            return
        # Update state via StateService
        if self._state_service.update_visual_config(
            self._current_state_key,
            bubble_visible=checked
        ):
            # Update UI
            self._bubble_visible = checked
            self._bubble_controller.set_visible(checked)

    def _rename_pet(self):
        # NEW: Update through StateService
        if not self._current_state_key:
            return
        current_state = self._state_service.get_state(self._current_state_key)
        if not current_state:
            return

        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename pet",
            "Name tag:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current_state.name_tag,
        )
        if ok and text.strip():
            # Update state via StateService
            if self._state_service.update_state(
                self._current_state_key,
                name_tag=text.strip()
            ):
                # Update local cache
                self._name_tag = text.strip()
            self.update()

    def _add_state(self, checked: bool = False) -> str | None:
        # NEW: Use dialog
        from .ui.dialogs.state import show_add_state_dialog
        return show_add_state_dialog(self._state_service, parent=self)

    def _remove_state_by_key(
        self,
        key: str,
        *,
        confirm: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        # NEW: Use StateService with confirmation
        if confirm:
            state = self._state_service.get_state(key)
            if not state:
                return False

            reply = QtWidgets.QMessageBox.question(
                parent or self,
                "Remove state",
                f"Remove state '{state.label}'?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return False

        return self._state_service.remove_state(key)

    def _remove_current_state(self):
        # NEW: Remove current state
        if self._current_state_key:
            self._remove_state_by_key(self._current_state_key, confirm=True)

    # --- Chat panel rendering --------------------------------------
    def _draw_text_panel(self, p: QtGui.QPainter, alpha: int):
        text = (self._bubble_text or "").strip()
        if not text or alpha <= 0:
            self._panel_rect_cache = None
            return

        target_width = max(160.0, float(self._sprite_size.width()))
        panel_width = max(
            80.0,
            min(target_width, float(self.width()) - 24.0),
        )

        inner_padding_x = tokens.spacing.bubble_inner_x
        inner_padding_y = tokens.spacing.bubble_inner_y
        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        metrics = QtGui.QFontMetrics(font)
        text_flags = int(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        text_flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
        available_text_width = max(60.0, panel_width - inner_padding_x * 2.0)
        text_metrics = metrics.boundingRect(
            QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
            text_flags,
            text,
        )
        text_height = max(float(metrics.lineSpacing()), float(text_metrics.height()))
        panel_height = max(self._panel_height_hint, text_height + inner_padding_y * 2.0)

        sprite_center = self._sprite_center()
        sprite_half_h = float(max(tokens.sprite.min_half_height, self._sprite_size.height() / 2.0))
        gap = tokens.spacing.sprite_bubble_gap
        margin_top = tokens.spacing.margin_top
        margin_bottom = tokens.spacing.margin_bottom

        below_top = sprite_center.y() + sprite_half_h + gap
        available_below = self.height() - margin_bottom - below_top
        above_bottom = sprite_center.y() - sprite_half_h - gap
        available_above = max(0.0, above_bottom - margin_top)

        place_below = True
        adjusted_panel_height = panel_height

        if available_below < adjusted_panel_height and available_above > available_below:
            adjusted_panel_height = min(adjusted_panel_height, available_above)
            place_below = False
        else:
            adjusted_panel_height = min(adjusted_panel_height, max(available_below, 0.0))
            if adjusted_panel_height <= 0.0 and available_above > 0.0:
                adjusted_panel_height = min(panel_height, available_above)
                place_below = False

        if adjusted_panel_height <= 0.0:
            adjusted_panel_height = min(panel_height, self.height() - margin_top - margin_bottom)

        if place_below:
            top = max(margin_top, below_top)
            if top + adjusted_panel_height + margin_bottom > self.height():
                adjusted_panel_height = max(0.0, self.height() - margin_bottom - top)
            self._bubble_side = "below"
        else:
            bottom_edge = min(above_bottom, self.height() - margin_bottom)
            top = max(margin_top, bottom_edge - adjusted_panel_height)
            self._bubble_side = "above"

        if adjusted_panel_height <= 0.0:
            self._panel_rect_cache = None
            return

        left = sprite_center.x() - panel_width / 2.0
        min_left = tokens.spacing.margin_horizontal
        max_left = self.width() - panel_width - tokens.spacing.margin_horizontal
        if max_left < min_left:
            min_left = max_left = max(self.width() - panel_width, 0.0)
        left = max(min_left, min(max_left, left))
        panel_rect = QtCore.QRectF(left, top, panel_width, adjusted_panel_height)

        shadow_rect = panel_rect.adjusted(
            0.0,
            tokens.spacing.shadow_offset_below if place_below else tokens.spacing.shadow_offset_above,
            0.0,
            tokens.spacing.shadow_extend_below if place_below else tokens.spacing.shadow_extend_above
        )
        corner_radius = tokens.radius.bubble

        base_alpha = max(tokens.opacity.min_base_alpha, min(tokens.opacity.max_base_alpha, alpha))
        outline_alpha = tokens.calculate_outline_alpha(base_alpha)
        fill_alpha = tokens.calculate_fill_alpha(base_alpha)

        fill_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.left(), panel_rect.bottom()),
        )
        fill_gradient.setColorAt(0.0, QtGui.QColor(255, 255, 255, fill_alpha))
        fill_gradient.setColorAt(1.0, QtGui.QColor(236, 240, 255, fill_alpha))

        outline_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.right(), panel_rect.bottom()),
        )
        outline_gradient.setColorAt(0.0, QtGui.QColor(134, 180, 255, outline_alpha))
        outline_gradient.setColorAt(1.0, QtGui.QColor(255, 255, 255, outline_alpha))

        sheen_clip = QtGui.QPainterPath()
        sheen_clip.addRoundedRect(
            panel_rect.adjusted(12.0, 12.0, -12.0, -panel_rect.height() * 0.55),
            corner_radius - 6.0,
            corner_radius - 6.0,
        )
        sheen_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.right(), panel_rect.top()),
        )
        sheen_gradient.setColorAt(0.0, QtGui.QColor(255, 255, 255, int(base_alpha * 0.28)))
        sheen_gradient.setColorAt(0.6, QtGui.QColor(255, 255, 255, int(base_alpha * 0.12)))
        sheen_gradient.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))

        text_rect = panel_rect.adjusted(inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y)

        text_option = QtGui.QTextOption(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        text_option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)

        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        shadow_color = QtGui.QColor(4, 8, 20, int(base_alpha * 0.4))
        shadow_path = QtGui.QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, corner_radius, corner_radius)
        p.fillPath(shadow_path, shadow_color)

        panel_path = QtGui.QPainterPath()
        panel_path.addRoundedRect(panel_rect, corner_radius, corner_radius)

        p.setBrush(QtGui.QBrush(fill_gradient))
        outline_pen = QtGui.QPen(QtGui.QBrush(outline_gradient), 2.6)
        outline_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(outline_pen)
        p.drawPath(panel_path)

        sheen_shape = panel_path.intersected(sheen_clip)
        if not sheen_shape.isEmpty():
            p.setBrush(QtGui.QBrush(sheen_gradient))
            p.setPen(QtCore.Qt.NoPen)
            p.drawPath(sheen_shape)

        text_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 255))

        p.setFont(font)
        p.setPen(text_pen)
        p.drawText(text_rect, text, text_option)

        p.restore()
        self._panel_rect_cache = QtCore.QRectF(panel_rect)

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
