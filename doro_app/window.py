"""Main application window and UI logic for Doro."""

from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .actions import ACTION_ALIASES
from .bubble_controller import BubbleConfig, BubbleController
from .chat_controller import ChatController
from .chat_orchestrator import ChatOrchestrator
from .movement_manager import MovementManager
from .models import MoveStateSettings
from .paths import ACTION_TRANSITION_DIR, CLICK_ACTIONS_PATH, COMPANION_PROMPTS_PATH, MOVE_DIR, PROMPT_PATH, STATE_DIR
from .state_models import State, StateChangeEvent
from .state_repository import GifRepository, MoveStateRepository, StateRepository
from .state_service import StateService
from .theme import ensure_application_theme
from .themed_menu import create_doro_menu
from .utils import safe_float as _safe_float, safe_int as _safe_int


class DoroWindow(QtWidgets.QWidget):
    def __init__(self, not_topmost: bool = False):
        super().__init__()
        ensure_application_theme()
        self.resize(380, 230)
        self.setMinimumSize(320, 240)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool  # hides from taskbar
        )
        if not not_topmost:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # Animation clock
        self._t = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS

        # Appearance/animation parameters
        # OLD state data removed - now managed by StateService
        self._active_gif_path: str | None = None
        self._current_state_key: str = ""
        self._state_list_text: str = ""
        self._movement_only_state_keys: set[str] = {"walking"}
        self._move_state_list_text: str = ""
        self._amplitude = 0.0
        self._scale_amp = 0.0
        self._fill_colors: tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor] = (
            QtGui.QColor("#FFFFFFFF"),
            QtGui.QColor("#FF9BE3FF"),
            QtGui.QColor("#FF6CC1F0"),
        )
        self._cheek_alpha = 0.0
        self._blush_base = QtGui.QColor("#FFC0C0")
        self._eye_color = QtGui.QColor("#222222")
        self._bubble_visible = True
        self._bubble_alpha = 170.0
        self._bubble_side = "center"
        self._name_tag = "doro"
        self._gif_movie: QtGui.QMovie | None = None
        self._bubble_text = ""
        self._bubble_text_show_override = False
        self._bubble_auto_hide_ms = 6000
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
        self._companion_prompts: list[str] = []
        self._companion_prompt_index = 0
        self._last_user_activity = time.monotonic()
        self._companion_idle_threshold = 10.0
        self._panel_width_hint = 360.0
        self._panel_height_hint = 110.0
        self._panel_rect_cache: QtCore.QRectF | None = None
        self._sprite_size = QtCore.QSize(200, 200)
        self._sprite_offset_x = -110.0
        self._sprite_anchor_top: float | None = None
        self._movement_step_px = 60
        self._default_move_state_key = "walking"
        # Removed: self._move_state_defs - now using StateService.all_move_state_keys()

        # NEW architecture - state management without Window coupling
        self._gif_repo = GifRepository(STATE_DIR)
        self._state_repo = StateRepository(STATE_DIR / "states.json")
        self._move_repo = MoveStateRepository(STATE_DIR / "move_states.json")
        self._state_service = StateService(
            self._state_repo,
            self._move_repo,
            self._gif_repo,
            STATE_DIR / "state_list.txt",
        )

        # Connect state change events
        self._state_service.on_state_changed = self._on_state_changed
        self._state_service.on_states_modified = self._on_states_modified

        self._bubble_controller = BubbleController(self)
        self._movement = MovementManager(self)
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
        self._companion_prompts_path = COMPANION_PROMPTS_PATH
        self._click_press_pos: QtCore.QPointF | None = None
        self._click_was_dragging = False

        # QSettings must be created before reading/writing
        self._config = QtCore.QSettings("doro-pet", "doro")

        # Write default idle.gif once (if user hasn't set any)
        if not self._config.contains("state/idle/gif_path") and self._default_idle_gif.is_file():
            self._config.setValue("state/idle/gif_path", str(self._default_idle_gif))

        offset_x = _safe_float(self._config.value("ui/bubble_offset_x", 120.0), 120.0)
        offset_y = _safe_float(self._config.value("ui/bubble_offset_y", -110.0), -110.0)
        scale_pref = _safe_float(self._config.value("ui/bubble_scale", 1.0), 1.0)
        self._bubble_controller.apply_persisted_config(
            BubbleConfig(offset_x=offset_x, offset_y=offset_y, scale=scale_pref, auto_hide_ms=self._bubble_auto_hide_ms)
        )
        self._apply_window_preferred_size()

        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_text_provider=lambda: self._state_list_text or "",
            movement_hint_provider=lambda: self._movement.instruction_text(),
            parent=self,
        )
        self._chat_orchestrator = ChatOrchestrator(self, self._chat_controller, self._movement)
        self._chat_cursor_overridden = False
        self._companion_prompts = self._load_companion_prompts()

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
        dt = min(dt, 0.1)
        self._movement.process_active_movement(dt)
        self._t += dt
        self.update()

    # --- Interaction -----------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._begin_bubble_transform(e.position()):
                self._update_bubble_cursor(e.position())
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
        if self._update_bubble_transform(e.position()):
            self._update_bubble_cursor(e.position())
            e.accept()
            return
        if not self._bubble_dragging and not self._bubble_resizing:
            self._update_bubble_cursor(e.position())
        if self._drag_pos is not None and e.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if (
                self._click_press_pos is not None
                and not self._click_was_dragging
                and (e.position() - self._click_press_pos).manhattanLength() > 6
            ):
                self._click_was_dragging = True
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._end_bubble_transform():
                self._update_bubble_cursor(e.position())
                e.accept()
                return
            was_click = (
                not self._click_was_dragging
                and self._click_press_pos is not None
                and (e.position() - self._click_press_pos).manhattanLength() <= 6
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
        self._update_bubble_cursor(None)
        super().leaveEvent(e)

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        self._mark_user_activity()
        super().keyPressEvent(e)

    def _sprite_center(self) -> QtCore.QPointF:
        base_x = self.width() / 2.0 + getattr(self, "_sprite_offset_x", 0.0)
        half_w = max(20.0, self._sprite_size.width() / 2.0)
        half_h = max(20.0, self._sprite_size.height() / 2.0)
        margin_x = 12.0
        min_center_x = half_w + margin_x
        max_center_x = self.width() - half_w - margin_x
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))
        bob_allowance = abs(getattr(self, "_amplitude", 0.0)) + 20.0
        margin_bottom = 24.0
        min_center_y = half_h + bob_allowance
        max_center_y = self.height() - half_h - margin_bottom
        if max_center_y < min_center_y:
            max_center_y = min_center_y
        if getattr(self, "_sprite_anchor_top", None) is None:
            panel_reserve = getattr(self, "_panel_height_hint", 110.0) + 48.0
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

    def _clamp_bubble_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        return self._bubble_controller.clamp_offset(candidate)

    def _apply_bubble_offset(self, candidate: QtCore.QPointF, *, persist: bool = False):
        self._bubble_controller.apply_offset(candidate, persist=persist)

    def _set_bubble_scale(self, value: float, *, persist: bool = False):
        self._bubble_controller.set_scale(value, persist=persist)

    def _persist_bubble_preferences(self):
        self._bubble_controller.persist_preferences()

    def _bubble_handle_rect(self) -> QtCore.QRectF | None:
        return None

    def _update_bubble_side_from_offset(self):
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

    def _normalize_state_token(self, token: str) -> str:
        raw = (token or "").strip()
        if not raw:
            return ""
        lowered = raw.lower()
        for prefix in ("state", "mode", "status"):
            if lowered.startswith(prefix):
                raw = raw[len(prefix) :]
                break
        else:
            if raw.startswith(("狀態", "模式")):
                raw = raw[2:]
        raw = raw.lstrip(":：-_ ")
        return raw.strip().lower()


    def _begin_bubble_transform(self, pos: QtCore.QPointF) -> bool:
        return self._bubble_controller.begin_transform(pos)

    def _update_bubble_transform(self, pos: QtCore.QPointF) -> bool:
        return self._bubble_controller.update_transform(pos)

    def _update_bubble_cursor(self, pos: QtCore.QPointF | None):
        self._bubble_controller.update_cursor(pos)

    def _end_bubble_transform(self) -> bool:
        return self._bubble_controller.end_transform()

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
        # Create Doro-themed menu with avatar from current GIF
        menu = create_doro_menu(
            parent=self,
            avatar_position="top-right",
            gif_movie=self._gif_movie
        )

        states_menu = menu.addMenu("States")
        for key in self._visible_state_keys():
            # NEW: Get state from StateService
            state = self._state_service.get_state(key)
            if not state:
                continue
            label = state.label or key
            action = states_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == self._current_state_key)
            action.triggered.connect(lambda checked, s=key: self._set_state(s))

        edit_states_action = states_menu.addAction("Edit states")
        edit_states_action.triggered.connect(self._show_state_gif_manager)

        remove_action = states_menu.addAction("Remove current state")
        remove_action.setEnabled(
            bool(self._current_state_key)
            and not self._state_service.is_state_protected(self._current_state_key)
        )
        remove_action.triggered.connect(self._remove_current_state)

        actions_menu = menu.addMenu("Actions")
        edit_actions_action = actions_menu.addAction("Edit actions")
        edit_actions_action.triggered.connect(self._show_move_gif_manager)

        menu.addSeparator()

        top_action = QtGui.QAction("Stay on top", self)
        top_action.setCheckable(True)
        is_top = bool(self.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)
        top_action.setChecked(is_top)

        def toggle_top():
            f = self.windowFlags()
            if bool(f & QtCore.Qt.WindowType.WindowStaysOnTopHint):
                f &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
            else:
                f |= QtCore.Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(f)
            self.show()  # re-apply flags

        top_action.triggered.connect(toggle_top)
        menu.addAction(top_action)

        visuals_menu = menu.addMenu("State visuals")
        bubble_action = visuals_menu.addAction("Show message panel")
        bubble_action.setCheckable(True)
        # NEW: Get from StateService
        current_state = self._state_service.get_current_state()
        bubble_action.setChecked(bool(current_state and current_state.visual.bubble_visible))
        bubble_action.triggered.connect(self._toggle_bubble)

        gif_action = visuals_menu.addAction("Load GIF")
        gif_action.triggered.connect(self._load_state_gif)

        clear_gif_action = visuals_menu.addAction("Reset GIF to default")
        clear_gif_action.setEnabled(self._default_idle_gif.is_file())
        clear_gif_action.triggered.connect(self._clear_state_gif)

        name_tag_action = visuals_menu.addAction("Rename pet")
        name_tag_action.triggered.connect(self._rename_pet)

        chat_menu = menu.addMenu("Chat")
        ask_action = chat_menu.addAction("Ask Doro")
        ask_action.setEnabled(not self._chat_orchestrator.is_inflight)
        ask_action.triggered.connect(self._prompt_chat)

        edit_prompt_action = chat_menu.addAction("Edit prompt")
        edit_prompt_action.triggered.connect(self._edit_chat_prompt)

        clear_history_action = chat_menu.addAction("Clear conversation history")
        clear_history_action.setEnabled(self._chat_controller.has_history)
        clear_history_action.triggered.connect(self._clear_chat_history)

        configure_menu = chat_menu.addMenu("Configure")

        server_action = configure_menu.addAction("Set server URL")
        server_action.triggered.connect(self._configure_chat_server)

        model_action = configure_menu.addAction("Set model name")
        model_action.triggered.connect(self._configure_chat_model)

        endpoint_action = configure_menu.addAction("Set endpoint path")
        endpoint_action.triggered.connect(self._configure_chat_endpoint)

        temperature_action = configure_menu.addAction("Set temperature")
        temperature_action.triggered.connect(self._configure_chat_temperature)

        timeout_action = configure_menu.addAction("Set timeout (seconds)")
        timeout_action.triggered.connect(self._configure_chat_timeout)

        menu.addSeparator()
        quit_action = QtGui.QAction("Exit doro", self)
        quit_action.triggered.connect(QtWidgets.QApplication.instance().quit)
        menu.addAction(quit_action)

        restart_action = QtGui.QAction("Restart doro", self)
        restart_action.triggered.connect(self._restart_app)
        menu.addAction(restart_action)

        menu.exec(e.globalPos())

    # --- Painting --------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Apply bob (vertical oscillation) and scale (breathing) animations
        bob = self._amplitude * math.sin(self._t * 2.0)
        scale = 1.0 + self._scale_amp * math.sin(self._t * 1.5)

        sprite_center = self._sprite_center()
        p.save()
        p.translate(sprite_center.x(), sprite_center.y() + bob)
        p.scale(scale, scale)

        if self._gif_movie and not self._gif_movie.currentPixmap().isNull():
            pixmap = self._gif_movie.currentPixmap()
            p.translate(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            p.drawPixmap(0, 0, pixmap)
        else:
            p.translate(-90, -90)

            path = QtGui.QPainterPath(QtCore.QPointF(90, 20))
            path.cubicTo(50, 20, 30, 50, 30, 90)
            path.cubicTo(30, 130, 50, 160, 90, 160)
            path.cubicTo(130, 160, 150, 130, 150, 90)
            path.cubicTo(150, 50, 130, 20, 90, 20)

            fill = QtGui.QLinearGradient(QtCore.QPointF(90, 20), QtCore.QPointF(90, 160))
            fill.setColorAt(0.0, self._fill_colors[0])
            fill.setColorAt(0.4, self._fill_colors[1])
            fill.setColorAt(1.0, self._fill_colors[2])

            p.setPen(QtGui.QPen(QtGui.QColor("#FF5C9ED6"), 3))
            p.setBrush(QtGui.QBrush(fill))
            p.drawPath(path)

            if self._cheek_alpha > 0:
                blush = QtGui.QColor(self._blush_base)
                blush.setAlpha(int(self._cheek_alpha))
                p.setBrush(blush)
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.drawEllipse(QtCore.QRectF(55, 85, 18, 10))
                p.drawEllipse(QtCore.QRectF(107, 85, 18, 10))

            p.setBrush(self._eye_color)
            p.drawEllipse(QtCore.QRectF(70, 70, 10, 14))
            p.drawEllipse(QtCore.QRectF(100, 70, 10, 14))

            self._draw_mouth(p)

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

    def _apply_card_shadow(
        self,
        widget: QtWidgets.QWidget,
        *,
        blur_radius: float = 28.0,
        y_offset: float = 10.0,
        opacity: int = 150,
    ):
        shadow = QtWidgets.QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur_radius)
        shadow.setOffset(0.0, y_offset)
        shadow.setColor(QtGui.QColor(4, 7, 20, opacity))
        widget.setGraphicsEffect(shadow)
    # --- State helpers ---------------------------------------------------

    # ═══════════════════════════════════════════════════════════
    # Public State API - Encapsulation Layer
    # ═══════════════════════════════════════════════════════════

    def has_state(self, key: str) -> bool:
        """Check if a state exists (public API)."""
        return self._state_service.has_state(key)

    def get_state(self, key: str) -> Optional[State]:
        """Get a state by key (public API)."""
        return self._state_service.get_state(key)

    def set_state(self, key: str) -> bool:
        """Change to a different state (public API)."""
        return self._state_service.set_state(key)

    def is_movement_only_state(self, key: str) -> bool:
        """Check if a state is movement-only (public API)."""
        return self._state_service.is_movement_only_state(key)

    def get_current_state_key(self) -> Optional[str]:
        """Get the current state key (public API)."""
        return self._current_state_key

    def save_states(self) -> bool:
        """Save all states to disk (public API)."""
        return self._state_service.save_states()

    def get_gif_path(self, resource_id: str) -> Optional[Path]:
        """Get GIF file path from resource ID (public API)."""
        return self._gif_repo.get_path(resource_id)

    # ═══════════════════════════════════════════════════════════
    # Event Callbacks from StateService
    # ═══════════════════════════════════════════════════════════

    # NEW: Event callbacks from StateService
    def _on_state_changed(self, event: StateChangeEvent) -> None:
        """
        Handle state change events from StateService.

        This replaces the old pattern where StateManager directly called Window methods.
        """
        state = event.new_state

        # Update current state tracking (for compatibility with old code)
        self._current_state_key = event.new_key
        self._state_list_text = self._state_service.write_state_list()

        # Pick and load random GIF variant
        gif_resource_id = self._state_service.pick_random_variant(event.new_key)
        if gif_resource_id:
            gif_path = self._gif_repo.get_path(gif_resource_id)
            if gif_path:
                self._load_gif(str(gif_path))

        # Apply visual config
        visual = state.visual
        self._amplitude = visual.bob_amplitude
        self._scale_amp = visual.scale_amplitude
        self._fill_colors = (
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._cheek_alpha = visual.cheeks_alpha
        self._blush_base = QtGui.QColor(visual.blush_color)
        self._eye_color = QtGui.QColor(visual.eye_color)
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
        """
        Resolve movement state configuration.

        Legacy method - converts new MoveState to old MoveStateSettings format.
        """
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

    def _persist_current_state(self):
        """Persist current state to QSettings. State data is handled by StateService."""
        if not self._current_state_key:
            return
        self._config.setValue("current_state", self._current_state_key)

    def _apply_state_settings(self):
        """
        Apply current state settings from StateService.

        This is a legacy method kept for compatibility. New code should use
        _on_state_changed() event handler instead.
        """
        if not self._current_state_key:
            return

        state = self._state_service.get_state(self._current_state_key)
        if not state:
            return

        # Apply visual config
        visual = state.visual
        self._amplitude = visual.bob_amplitude
        self._scale_amp = visual.scale_amplitude
        self._fill_colors = (
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._cheek_alpha = visual.cheeks_alpha
        self._blush_base = QtGui.QColor(visual.blush_color)
        self._eye_color = QtGui.QColor(visual.eye_color)
        self._bubble_visible = visual.bubble_visible
        self._bubble_alpha = visual.bubble_alpha
        self._name_tag = state.name_tag

        # Load GIF variant
        gif_resource_id = self._state_service.pick_random_variant(self._current_state_key)
        if gif_resource_id:
            gif_path = self._gif_repo.get_path(gif_resource_id)
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
        if self._gif_movie:
            try:
                self._gif_movie.frameChanged.disconnect(self._on_movie_frame_changed)
            except (RuntimeError, TypeError):
                pass
            self._gif_movie.stop()
            self._gif_movie = None

        if not path:
            self._update_sprite_size_hint(None)
            return

        path_obj = Path(path)
        if not path_obj.is_file():
            self._update_sprite_size_hint(None)
            return

        movie = QtGui.QMovie(str(path_obj))
        if not movie.isValid():
            self._update_sprite_size_hint(None)
            return

        movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(self._on_movie_frame_changed)
        movie.start()
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

    def _select_state_gif_variant(self, key: str):
        """
        Select and load a random GIF variant for the given state.

        This is a legacy method. New code should use StateService.pick_random_variant().
        """
        gif_resource_id = self._state_service.pick_random_variant(key)
        if gif_resource_id:
            gif_path = self._gif_repo.get_path(gif_resource_id)
            if gif_path:
                self._active_gif_path = str(gif_path)
                return

        # Fallback to default idle GIF
        if self._default_idle_gif.is_file():
            try:
                self._active_gif_path = str(self._default_idle_gif.resolve())
            except OSError:
                self._active_gif_path = str(self._default_idle_gif)
        else:
            self._active_gif_path = None

    def _set_state(self, key: str):
        # NEW: Use StateService
        self._state_service.set_state(key)

    def _load_state_gif(self):
        # NEW: Show GIF manager dialog
        from .state_dialogs import show_state_gif_manager
        show_state_gif_manager(self._state_service, parent=self)

    def _set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        # NEW: Use StateService
        return self._state_service.set_primary_gif(key, Path(source_path))

    def _add_state_gif_variant_from_path(self, key: str, source_path: str) -> bool:
        # NEW: Use StateService
        return self._state_service.add_gif_variant(key, Path(source_path))

    def _remove_state_gif_variant(
        self,
        key: str,
        variant_path: str,
        *,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        # NEW: variant_path is now a resource_id
        return self._state_service.remove_gif_variant(key, variant_path)

    def _write_state_list(self):
        # NEW: Delegate to StateService
        self._state_list_text = self._state_service.write_state_list()

    def _write_move_state_list(self):
        """Write movement state list (NEW: uses StateService)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的移動狀態為:"]

        # NEW: Get movement states from StateService
        move_keys = self._state_service.all_move_state_keys()
        if not move_keys:
            lines.append("- (none) 無移動專用狀態")
        else:
            for key in sorted(move_keys):
                move_state = self._state_service.get_move_state(key)
                if not move_state:
                    continue

                direction = (move_state.direction or "any").strip() or "any"
                direction = direction.lower()
                state_key = move_state.state_key

                # Get state information from StateService
                state = self._state_service.get_state(state_key)
                label = state.label if state else state_key

                # Get GIF information
                gif_hint = "(no GIF)"
                if state and state.primary_gif_id:
                    gif_path = self._gif_repo.get_path(state.primary_gif_id)
                    if gif_path:
                        gif_hint = str(gif_path)

                lines.append(
                    f"- ({key}) {label} | direction: {direction} | state: {state_key} | GIF: {gif_hint}"
                )

        output = "\n".join(lines) + "\n"
        self._move_state_list_text = output.strip()
        try:
            self._move_state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    def _show_state_gif_collection(self, state_key: str, *, parent: QtWidgets.QWidget | None = None):
        # NEW: Use dialog
        from .state_dialogs import show_gif_variant_dialog
        show_gif_variant_dialog(self._state_service, state_key, parent=parent or self)

    def _show_state_gif_manager(self):
        # NEW: Use dialog
        from .state_dialogs import show_state_gif_manager
        show_state_gif_manager(self._state_service, parent=self)

    def _show_move_gif_manager(self):
        # TODO: Implement move GIF manager with new architecture
        QtWidgets.QMessageBox.information(
            self,
            "Move GIF Manager",
            "Move states not yet migrated to new architecture.\nComing soon!",
        )

    def _clear_state_gif(self):
        # NEW: Clear primary GIF for current state
        if self._current_state_key:
            state = self._state_service.get_state(self._current_state_key)
            if state and state.primary_gif_id:
                self._gif_repo.delete(state.primary_gif_id)
                self._state_service.update_state(self._current_state_key, primary_gif_id=None)

    def _load_click_actions(self) -> list[str]:
        path = getattr(self, "_click_actions_path", None)
        if not path:
            return []
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _load_companion_prompts(self) -> list[str]:
        path = getattr(self, "_companion_prompts_path", None)
        prompts: list[str] = []
        if path:
            try:
                raw = Path(path).read_text(encoding="utf-8")
            except OSError:
                raw = ""
            if raw:
                prompts = [line.strip() for line in raw.splitlines() if line.strip()]
        if not prompts:
            prompts = [
                "請主動示範一個陪伴主人的小動作，務必搭配適當的括號狀態或方括號移動，並附上一句溫暖關懷的短句。",
                "想辦法吸引主人的注意，安排一個活潑的小劇情，記得輸出必要的 (STATE: ...) 或 [MOVE:...] 指令。",
                "描述 Doro 此刻的心情並配上一個生動的動作，簡短一句話即可，務必包含行為指令讓動畫能執行。",
            ]
        return prompts

    def _next_companion_prompt(self) -> str:
        if not self._companion_prompts:
            return ""
        prompt = self._companion_prompts[self._companion_prompt_index % len(self._companion_prompts)]
        self._companion_prompt_index = (self._companion_prompt_index + 1) % len(self._companion_prompts)
        return prompt

    def _on_companion_timeout(self):
        if self._chat_orchestrator.is_inflight:
            return
        if not self.isVisible():
            return
        if self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
            return
        now = time.monotonic()
        if now - self._last_user_activity < self._companion_idle_threshold:
            return
        prompt = self._next_companion_prompt()
        if not prompt:
            return
        self._last_user_activity = now
        self._chat_orchestrator.send_message(prompt, silent=True, is_auto=True)

    def _trigger_click_action(self):
        self._mark_user_activity()
        actions = self._load_click_actions()
        if not actions or self._chat_orchestrator.is_inflight:
            return
        message = random.choice(actions).strip()
        if not message:
            return
        self._chat_orchestrator.send_message(message)

    def _find_state_for_action(self, action: str) -> str | None:
        normalized = self._normalize_state_token(action)
        if not normalized:
            return None

        # Check aliases
        alias_target = ACTION_ALIASES.get(normalized)
        if alias_target and self._state_service.get_state(alias_target):
            if not self._is_movement_only_state(alias_target):
                return alias_target

        # Try various normalized forms
        candidates = {
            normalized,
            normalized.replace(" ", "_"),
            normalized.replace(" ", ""),
        }
        sanitized = "".join(ch for ch in normalized if ch.isalnum() or ch in ("-", "_"))
        if sanitized:
            candidates.add(sanitized)

        for candidate in candidates:
            if self._state_service.get_state(candidate):
                if not self._is_movement_only_state(candidate):
                    return candidate

        # Try matching by label
        result = self._state_service.find_state_by_label(normalized)
        if result and not self._is_movement_only_state(result):
            return result

        return None

    def _set_busy_cursor(self, enabled: bool):
        if enabled and not self._chat_cursor_overridden:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
            self._chat_cursor_overridden = True
        elif not enabled and self._chat_cursor_overridden:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._chat_cursor_overridden = False

    def _prompt_chat(self):
        if self._chat_orchestrator.is_inflight:
            QtWidgets.QMessageBox.information(
                self,
                "Chat",
                "I'm already replying, please wait a little bit.",
            )
            return
        self._mark_user_activity()
        prompt, ok = QtWidgets.QInputDialog.getMultiLineText(
            self,
            "Chat with Doro",
            "Say something to Doro:",
            "",
        )
        if not ok:
            return
        cleaned = prompt.strip()
        if not cleaned:
            return
        self._chat_orchestrator.send_message(cleaned)

    def _clear_chat_history(self):
        if not self._chat_controller.has_history:
            self._clear_bubble_text()
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear conversation",
            "Clear Doro's recent conversation history?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._chat_controller.clear_history()
        self._clear_bubble_text()

    def _edit_chat_prompt(self):
        descriptive_path = str(self._prompt_file_path)
        current = self._chat_controller.system_prompt or ""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self,
            "Edit Doro prompt",
            f"Prompt stored at:\n{descriptive_path}\n\nEnter new prompt:",
            current,
        )
        if not ok:
            return
        cleaned = text.strip()
        if not cleaned:
            QtWidgets.QMessageBox.warning(
                self,
                "Edit Doro prompt",
                "Prompt cannot be empty.",
            )
            return
        try:
            self._chat_controller.update_system_prompt(cleaned + "\n")
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Edit Doro prompt",
                f"Failed to write prompt file:\n{exc}",
            )
            return

    def _configure_chat_server(self):
        current = self._chat_controller.server_url or ""
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Chat server URL",
            "Base server URL (e.g. http://127.0.0.1:1234):",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        new_url = text.strip()
        if not new_url:
            QtWidgets.QMessageBox.warning(self, "Chat server URL", "URL cannot be empty.")
            return
        self._chat_controller.set_server_url(new_url)

    def _configure_chat_model(self):
        current = self._chat_controller.model or ""
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Chat model name",
            "Model identifier:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        cleaned = text.strip()
        if not cleaned:
            QtWidgets.QMessageBox.warning(self, "Chat model name", "Model name cannot be empty.")
            return
        self._chat_controller.set_model(cleaned)

    def _configure_chat_endpoint(self):
        current = self._chat_controller.endpoint_path or "/v1/chat/completions"
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Chat endpoint path",
            "Endpoint path on the server:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        cleaned = text.strip()
        if not cleaned:
            QtWidgets.QMessageBox.warning(self, "Chat endpoint path", "Endpoint path cannot be empty.")
            return
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        self._chat_controller.set_endpoint_path(cleaned)

    def _configure_chat_temperature(self):
        value, ok = QtWidgets.QInputDialog.getDouble(
            self,
            "Chat temperature",
            "Sampling temperature:",
            float(self._chat_controller.temperature),
            0.0,
            2.0,
            decimals=2,
        )
        if not ok:
            return
        self._chat_controller.set_temperature(value)

    def _configure_chat_timeout(self):
        value, ok = QtWidgets.QInputDialog.getInt(
            self,
            "Chat timeout",
            "Request timeout in seconds:",
            int(self._chat_controller.timeout_seconds),
            5,
            120,
        )
        if not ok:
            return
        self._chat_controller.set_timeout_seconds(value)

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
        from .state_dialogs import show_add_state_dialog
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

    def _persist_state_definitions(self):
        # NEW: Persistence handled by StateService
        self._state_service.save_states()

    def _state_storage_token(self, key: str) -> str:
        # NEW: Use GifRepository public API
        return self._gif_repo.sanitize_filename(key)

    def _state_storage_path_for_key(self, key: str) -> Path:
        # NEW: Use GifRepository public API
        return self._gif_repo.get_state_storage_path(key)

    def _state_variants_dir_for_key(self, key: str) -> Path:
        # NEW: Use GifRepository public API
        return self._gif_repo.get_state_variants_dir(key)

    def _move_storage_path_for_key(self, key: str) -> Path:
        # NEW: Use GifRepository public API
        return self._gif_repo.get_move_storage_path(key)

    def _apply_move_gif_update(self, action_key: str):
        """
        Update GIF for a movement action.

        This is called when a move GIF is changed and needs to update the
        corresponding display state.
        """
        normalized = (action_key or "").strip().lower()
        if not normalized:
            return

        # NEW: Get move state from StateService
        move_state = self._state_service.get_move_state(normalized)
        if not move_state:
            return

        # Get GIF path for this move
        target_path = self._move_storage_path_for_key(normalized)
        if not target_path.is_file():
            return

        # Update corresponding display state
        state_key = move_state.state_key
        state = self._state_service.get_state(state_key)
        if not state:
            return

        # Set the move GIF as the primary GIF for this state
        if self._state_service.set_primary_gif(state_key, target_path):
            # Refresh state list
            self._write_state_list()
            self._write_move_state_list()

            # If this is the current state, trigger update
            if state_key == self._current_state_key:
                self._apply_state_settings()
                self.update()

    def _update_state_variants(self, key: str):
        """
        Refresh GIF variants for a state.

        This is a legacy method. StateService handles variant management automatically.
        """
        self._state_service.refresh_gif_variants(key)

    def _ensure_local_gif_for_state(self, key: str):
        """
        Ensure a state has a GIF assigned.

        This is a legacy method. GifRepository now handles all GIF storage
        automatically through store_gif().
        """
        state = self._state_service.get_state(key)
        if not state:
            return

        # If state already has a GIF, nothing to do
        if state.primary_gif_id:
            return

        # Special handling for walking state
        if key == "walking":
            walking_source = self._move_storage_dir / "walking.gif"
            if walking_source.is_file():
                self._state_service.set_primary_gif(key, walking_source)
                return

        # Fallback to default idle GIF if available
        if self._default_idle_gif.is_file():
            self._state_service.set_primary_gif(key, self._default_idle_gif)

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

        inner_padding_x = 28.0
        inner_padding_y = 22.0
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
        sprite_half_h = float(max(20.0, self._sprite_size.height() / 2.0))
        gap = 28.0
        margin_top = 18.0
        margin_bottom = 24.0

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
        min_left = 12.0
        max_left = self.width() - panel_width - 12.0
        if max_left < min_left:
            min_left = max_left = max(self.width() - panel_width, 0.0)
        left = max(min_left, min(max_left, left))
        panel_rect = QtCore.QRectF(left, top, panel_width, adjusted_panel_height)

        shadow_rect = panel_rect.adjusted(0.0, 8.0 if place_below else -12.0, 0.0, 12.0 if place_below else 4.0)
        corner_radius = 18.0

        base_alpha = max(140, min(255, alpha))
        outline_alpha = int(base_alpha * 0.55)
        fill_alpha = int(base_alpha * 0.92)

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

        def _classify_action_token(self, token: str, *, strict: bool = True):
            """
            解析括號指令：
            - (state: <key>) -> ("state", <key>)
            - (move:  <dir>) -> ("move", <normalized_direction_tuple>)
            嚴格模式(strict=True)僅接受有命名空間的格式；鬆綁時會回退到原本的容錯（先判斷移動，再嘗試狀態）。
            """
            raw = (token or "").strip()
            if not raw:
                return None

            # 1) 明確命名空間
            if ":" in raw:
                head, tail = raw.split(":", 1)
                ns = head.strip().lower()
                arg = tail.strip()
                if ns == "move":
                    direction = self._movement.parse_movement_token(arg)
                    return ("move", direction) if direction else None
                if ns == "state":
                    state_key = self._find_state_for_action(arg)
                    return ("state", state_key) if state_key else None
                # 未知命名空間直接忽略
                return None

            # 2) 嚴格模式：沒有命名空間就直接忽略，避免誤判
            if strict:
                return None

            # 3) 寬鬆容錯（跟現有邏輯一致）：先當「移動」試，失敗再當「狀態」
            direction = self._movement.parse_movement_token(raw)
            if direction:
                return ("move", direction)
            state_key = self._find_state_for_action(raw)
            if state_key:
                return ("state", state_key)
            return None
        
    def _clear_bubble_text(self):
        self._bubble_controller.clear_text()

    def _draw_mouth(self, p: QtGui.QPainter):
        pen = QtGui.QPen(QtGui.QColor(51, 51, 51))
        pen.setWidthF(2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)

        mouth = QtGui.QPainterPath()
        mouth.moveTo(80, 95)
        mouth.cubicTo(90, 105, 100, 105, 110, 95)
        p.drawPath(mouth)
    def _release_single_instance_locks_safely(self):
        """Release possible single-instance locks safely."""
        # QLockFile 常見做法
        for attr in ("_lock_file", "_instance_lock", "lock_file", "instance_lock"):
            lf = getattr(self, attr, None)
            # QLockFile: has isLocked()/unlock()
            try:
                if lf and hasattr(lf, "isLocked") and lf.isLocked() and hasattr(lf, "unlock"):
                    lf.unlock()
            except Exception:
                pass

        # QSharedMemory 常見做法
        for attr in ("_shared_mem", "shared_mem", "single_instance_shm"):
            shm = getattr(self, attr, None)
            try:
                if shm and hasattr(shm, "isAttached") and shm.isAttached() and hasattr(shm, "detach"):
                    shm.detach()
            except Exception:
                pass

        # 也可順手把參考清掉，避免之後誤用
        for attr in ("_lock_file", "_instance_lock", "lock_file", "instance_lock", "_shared_mem", "shared_mem", "single_instance_shm"):
            if hasattr(self, attr):
                try:
                    setattr(self, attr, None)
                except Exception:
                    pass

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._set_busy_cursor(False)
        timer = getattr(self, "_companion_timer", None)
        if isinstance(timer, QtCore.QTimer):
            timer.stop()
        super().closeEvent(event)
    def _restart_app(self):
        """Restart doro *without* external helper script."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        # 1) 儘量清理資源（避免檔案/鎖佔用）
        try:
            if getattr(self, "_gif_movie", None):
                try:
                    self._gif_movie.stop()
                except Exception:
                    pass
                self._gif_movie = None
            if hasattr(self, "_timer") and self._timer:
                try:
                    self._timer.stop()
                except Exception:
                    pass
            if getattr(self, "_config", None):
                self._config.sync()
        except Exception:
            pass

        # 2) 釋放可能的「單實例鎖」
        self._release_single_instance_locks_safely()

        # 3) 構造重新啟動命令列
        relaunch_cmd = self._build_self_launch_command()
        if not relaunch_cmd:
            QtWidgets.QMessageBox.warning(self, "Restart", "Unable to determine relaunch command.")
            return
        if "--restarted" not in relaunch_cmd:
            relaunch_cmd.append("--restarted")

        # 4) Debugger 下優先改用 execv，避免 IDE 把新行程一同停下
        debugger_attached = bool(getattr(sys, "gettrace", lambda: None)())
        if debugger_attached:
            try:
                os.execv(relaunch_cmd[0], relaunch_cmd)
                return  # pragma: no cover - execv 不會返回
            except Exception:
                debugger_attached = False  # 失敗時 fallback 至舊流程

        # 5) 以分離行程啟動自己
        cwd = str(Path(__file__).resolve().parent)
        ok, _pid = QtCore.QProcess.startDetached(relaunch_cmd[0], relaunch_cmd[1:], cwd)

        if ok:
            # 6) 啟動成功就關閉目前實例
            QtCore.QTimer.singleShot(50, app.quit)
        else:
            QtWidgets.QMessageBox.warning(self, "Restart", "Failed to relaunch doro. Please restart manually.")

    def _build_self_launch_command(self) -> list[str] | None:
        """Return argv for relaunching this app."""
        try:
            if getattr(sys, "frozen", False):  # PyInstaller 等
                exe = sys.executable or sys.argv[0]
                return [exe, *sys.argv[1:]] if exe else None

            python_exe = sys.executable or "python"

            # ★ Windows：若是 python.exe，優先改用 pythonw.exe（避免新行程被 console 關掉）
            if os.name == "nt":
                try:
                    base = os.path.dirname(python_exe)
                    name = os.path.basename(python_exe).lower()
                    if name == "python.exe":
                        cand = os.path.join(base, "pythonw.exe")
                        if os.path.isfile(cand):
                            python_exe = cand
                except Exception:
                    pass

            script_path = Path(sys.argv[0]).resolve()
            if not script_path.exists():
                script_path = Path(__file__).resolve()
            if not script_path.exists():
                return None
            return [python_exe, str(script_path), *sys.argv[1:]]
        except Exception:
            return None
