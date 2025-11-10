"""Main application window and UI logic for Doro."""

from __future__ import annotations

import copy
import json
import os
import random
import re
import shutil
import sys
import time
from dataclasses import asdict, fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .actions import ACTION_ALIASES
from .bubble_controller import BubbleConfig, BubbleController
from .chat_controller import ChatController
from .chat_orchestrator import ChatOrchestrator
from .movement_manager import MovementManager
from .models import MoveStateSettings, StateSettings
from .paths import ACTION_TRANSITION_DIR, CLICK_ACTIONS_PATH, COMPANION_PROMPTS_PATH, MOVE_DIR, PROMPT_PATH, STATE_DIR
from .state_manager import StateManager
from .theme import ensure_application_theme
from .utils import safe_float as _safe_float, safe_int as _safe_int
from .ui import ChatSettingsDialog, ContextMenuManager, WindowRenderer


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

        # Appearance/animation parameters (populated in _init_states)
        self._state_defs: dict[str, StateSettings] = {}
        self._protected_state_keys: set[str] = set()
        self._state_settings: StateSettings | None = None
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
        self._move_state_defs: dict[str, MoveStateSettings] = {}
        self._state_manager = StateManager(self)
        self._bubble_controller = BubbleController(self)
        self._movement = MovementManager(self)
        self._renderer = WindowRenderer(self, self._bubble_controller, self._movement)
        self._timer.timeout.connect(self._renderer.tick)
        self._timer.start(16)  # ~60 FPS
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
        self.apply_window_preferred_size()

        self._chat_controller = ChatController(
            self._config,
            self._prompt_file_path,
            state_text_provider=lambda: self._state_list_text or "",
            movement_hint_provider=lambda: self._movement.instruction_text(),
            parent=self,
        )
        self._chat_orchestrator = ChatOrchestrator(self, self._chat_controller, self._movement)
        self._chat_settings = ChatSettingsDialog(self, self._chat_controller)
        self._context_menu = ContextMenuManager(self, self._chat_settings)
        self._chat_cursor_overridden = False
        self._companion_prompts = self._load_companion_prompts()

        self._state_manager.init_states()
        self._state_manager.init_move_states()
        self._state_manager.restore_state_from_config()

        # self._companion_timer = QtCore.QTimer(self)
        # self._companion_timer.setInterval(10000)
        # self._companion_timer.timeout.connect(self._on_companion_timeout)
        # self._companion_timer.start()

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

    # --- Public accessors ------------------------------------------------

    @property
    def state_definitions(self) -> dict[str, StateSettings]:
        return self._state_defs

    @property
    def current_state_key(self) -> str:
        return self._current_state_key

    @property
    def protected_state_keys(self) -> set[str]:
        return self._protected_state_keys

    @property
    def state_settings(self) -> StateSettings | None:
        return self._state_settings

    @property
    def default_idle_gif_exists(self) -> bool:
        return self._default_idle_gif.is_file()

    @property
    def chat_orchestrator(self) -> ChatOrchestrator:
        return self._chat_orchestrator

    @property
    def chat_controller(self) -> ChatController:
        return self._chat_controller

    @property
    def state_manager(self) -> StateManager:
        return self._state_manager

    @property
    def movement_manager(self) -> MovementManager:
        return self._movement

    def visible_state_keys(self) -> list[str]:
        return self._state_manager.visible_state_keys()

    @property
    def bubble_offset(self) -> QtCore.QPointF:
        return self._bubble_offset

    @property
    def movement_step_px(self) -> int:
        return self._movement_step_px

    @property
    def default_move_state_key(self) -> str:
        return self._default_move_state_key

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

    def mark_user_activity(self):
        self._last_user_activity = time.monotonic()

    _mark_user_activity = mark_user_activity

    def _clamp_bubble_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        return self._bubble_controller.clamp_offset(candidate)

    def apply_bubble_offset(self, candidate: QtCore.QPointF, *, persist: bool = False):
        self._bubble_controller.apply_offset(candidate, persist=persist)

    _apply_bubble_offset = apply_bubble_offset

    def _set_bubble_scale(self, value: float, *, persist: bool = False):
        self._bubble_controller.set_scale(value, persist=persist)

    def _persist_bubble_preferences(self):
        self._bubble_controller._persist_preferences()

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

    def clamp_window_position(self, desired: QtCore.QPoint) -> QtCore.QPoint:
        geo = self.frameGeometry()
        rect = self._available_screen_geometry()
        max_x = rect.left() + max(0, rect.width() - geo.width())
        max_y = rect.top() + max(0, rect.height() - geo.height())
        min_x = rect.left()
        min_y = rect.top()
        clamped_x = max(min_x, min(max_x, desired.x()))
        clamped_y = max(min_y, min(max_y, desired.y()))
        return QtCore.QPoint(clamped_x, clamped_y)

    _clamp_window_position = clamp_window_position

    def move_window_to(self, point: QtCore.QPoint):
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

    _move_window_to = move_window_to

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

    def reset_animation_clock(self) -> None:
        self._renderer.reset_clock()

    def apply_window_preferred_size(self):
        self._renderer.apply_window_preferred_size()

    _apply_window_preferred_size = apply_window_preferred_size

    def update_sprite_size_hint(self, movie: QtGui.QMovie | None):
        self._renderer.update_sprite_size_hint(movie)

    _update_sprite_size_hint = update_sprite_size_hint

    def contextMenuEvent(self, e: QtGui.QContextMenuEvent):
        self._context_menu.exec(e)

    # --- Painting --------------------------------------------------------
    def paintEvent(self, event: QtGui.QPaintEvent):
        del event  # unused
        self._renderer.paint()

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
    def _init_states(self):
        self._state_manager.init_states()

    def _load_custom_states(self):
        self._state_manager._load_custom_states()

    def _init_move_states(self):
        self._state_manager.init_move_states()

    def _is_movement_only_state(self, key: str) -> bool:
        return self._state_manager.is_movement_only_state(key)

    def _visible_state_keys(self) -> list[str]:
        return self._state_manager.visible_state_keys()

    def _register_move_state(
        self,
        key: str,
        *,
        state_key: str,
        direction: str | None = None,
        default_distance: float | None = None,
        default_speed: str | None = None,
    ):
        return self._state_manager.register_move_state(
            key,
            state_key=state_key,
            direction=direction,
            default_distance=default_distance,
            default_speed=default_speed,
        )

    def _resolve_move_state(self, key: str | None) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        return self._state_manager.resolve_move_state(key)

    def _restore_state_from_config(self):
        self._state_manager.restore_state_from_config()

    def _persist_current_state(self):
        if not self._current_state_key:
            return
        self._config.setValue("current_state", self._current_state_key)
        if self._state_settings:
            path = self._state_settings.gif_path or ""
            self._config.setValue(f"state/{self._current_state_key}/gif_path", path)

    def apply_state_settings(self):
        self._renderer.apply_state_settings()

    _apply_state_settings = apply_state_settings

    def _on_movie_frame_changed(self, frame: int):
        self._renderer.on_movie_frame_changed(frame)

    def _select_state_gif_variant(self, key: str):
        if self._state_settings is None:
            self._active_gif_path = None
            return
        settings = self._state_settings
        candidates: list[str] = []
        for path in settings.gif_variants:
            try:
                candidate = Path(path)
            except TypeError:
                continue
            if candidate.is_file():
                try:
                    resolved = str(candidate.resolve())
                except OSError:
                    resolved = str(candidate)
                if resolved not in candidates:
                    candidates.append(resolved)
        base_path = settings.gif_path
        base_resolved: str | None = None
        if base_path:
            try:
                base_candidate = Path(base_path)
            except TypeError:
                base_candidate = None
            if base_candidate and base_candidate.is_file():
                try:
                    base_resolved = str(base_candidate.resolve())
                except OSError:
                    base_resolved = str(base_candidate)
                if base_resolved not in candidates:
                    candidates.insert(0, base_resolved)
        chosen: str | None
        if candidates:
            chosen = random.choice(candidates)
        elif base_resolved:
            chosen = base_resolved
        elif self._default_idle_gif.is_file():
            try:
                chosen = str(self._default_idle_gif.resolve())
            except OSError:
                chosen = str(self._default_idle_gif)
        else:
            chosen = None
        if chosen and not Path(chosen).is_file():
            chosen = None
        if chosen and base_resolved and chosen == base_resolved:
            self._active_gif_path = None
        else:
            self._active_gif_path = chosen

    def set_state(self, key: str):
        self._state_manager.set_state(key)

    _set_state = set_state

    def _reset_state_overrides(self):
        self._state_manager.reset_state_overrides()

    def load_state_gif(self):
        self._state_manager.load_state_gif()

    _load_state_gif = load_state_gif

    def _set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        return self._state_manager.set_state_gif_from_path(key, source_path)

    def _add_state_gif_variant_from_path(self, key: str, source_path: str) -> bool:
        return self._state_manager.add_state_gif_variant_from_path(key, source_path)

    def _remove_state_gif_variant(
        self,
        key: str,
        variant_path: str,
        *,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        return self._state_manager.remove_state_gif_variant(key, variant_path, parent=parent)

    def _write_state_list(self):
        if not self._state_defs:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的狀態為:"]
        visible_keys = sorted(self._visible_state_keys())
        for key in visible_keys:
            state = self._state_defs[key]
            label = state.label or key
            gif_hint = state.gif_path or "(no GIF)"
            variants_count = 0
            if state.gif_variants:
                unique_variants = []
                for path in state.gif_variants:
                    if path and path not in unique_variants:
                        unique_variants.append(path)
                variants_count = max(0, len(unique_variants) - (1 if state.gif_path else 0))
            if variants_count > 0:
                gif_hint = f"{gif_hint} (+{variants_count} variants)"
            lines.append(f"- ({key}) {label} | GIF: {gif_hint}")
        output = "\n".join(lines) + "\n"
        self._state_list_text = output.strip()
        try:
            self._state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    def _write_move_state_list(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的移動狀態為:"]
        if not self._move_state_defs:
            lines.append("- (none) 無移動專用狀態")
        else:
            for key in sorted(self._move_state_defs.keys()):
                move_settings = self._move_state_defs[key]
                direction = (move_settings.direction or "any").strip() or "any"
                direction = direction.lower()
                state_key = move_settings.state_key
                state_settings = self._state_defs.get(state_key)
                label = state_settings.label if state_settings else state_key
                gif_hint = (
                    state_settings.gif_path
                    if state_settings and state_settings.gif_path
                    else "(no GIF)"
                )
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
        self._state_manager.show_state_gif_collection(state_key, parent=parent)

    def _show_state_gif_manager(self):
        self._state_manager.show_state_gif_manager()

    def _show_move_gif_manager(self):
        self._state_manager.show_move_gif_manager()

    def clear_state_gif(self):
        self._state_manager.clear_state_gif(self._current_state_key or "")

    _clear_state_gif = clear_state_gif

    def load_gif(self, path: str | None):
        self._renderer.load_gif(path)

    _load_gif = load_gif

    def resolve_move_state(self, key: str | None) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        return self._state_manager.resolve_move_state(key)

    _resolve_move_state = resolve_move_state

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

    def find_state_for_action(self, action: str) -> str | None:
        normalized = self._normalize_state_token(action)
        if not normalized or not self._state_defs:
            return None

        alias_target = ACTION_ALIASES.get(normalized)
        if (
            alias_target
            and alias_target in self._state_defs
            and not self._is_movement_only_state(alias_target)
        ):
            return alias_target

        candidates = {
            normalized,
            normalized.replace(" ", "_"),
            normalized.replace(" ", ""),
        }
        sanitized = "".join(ch for ch in normalized if ch.isalnum() or ch in ("-", "_"))
        if sanitized:
            candidates.add(sanitized)

        for candidate in candidates:
            if candidate in self._state_defs and not self._is_movement_only_state(candidate):
                return candidate

        for key, settings in self._state_defs.items():
            label = (settings.label or "").strip().lower()
            if label and label == normalized and not self._is_movement_only_state(key):
                return key

        return None

    _find_state_for_action = find_state_for_action

    def set_busy_cursor(self, enabled: bool):
        if enabled and not self._chat_cursor_overridden:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
            self._chat_cursor_overridden = True
        elif not enabled and self._chat_cursor_overridden:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._chat_cursor_overridden = False

    _set_busy_cursor = set_busy_cursor

    def prompt_chat(self):
        if self._chat_orchestrator.is_inflight:
            QtWidgets.QMessageBox.information(
                self,
                "Chat",
                "I'm already replying, please wait a little bit.",
            )
            return
        self.mark_user_activity()
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

    _prompt_chat = prompt_chat

    def clear_chat_history(self):
        if not self._chat_controller.has_history:
            self.clear_chat_message()
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
        self.clear_chat_message()

    _clear_chat_history = clear_chat_history

    def edit_chat_prompt(self):
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

    _edit_chat_prompt = edit_chat_prompt

    def toggle_bubble(self, checked: bool):
        if self._state_settings is None:
            return
        self._bubble_controller.set_visible(checked)
        self._save_state_settings()

    _toggle_bubble = toggle_bubble

    def rename_pet(self):
        if self._state_settings is None:
            return
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename pet",
            "Name tag:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            self._state_settings.name_tag,
        )
        if ok and text.strip():
            self._state_settings.name_tag = text.strip()
            self.apply_state_settings()
            self.update()
            self._save_state_settings()

    _rename_pet = rename_pet

    def _add_state(self, checked: bool = False) -> str | None:
        del checked
        return self._state_manager.add_state()

    def _remove_state_by_key(
        self,
        key: str,
        *,
        confirm: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        return self._state_manager.remove_state_by_key(key, confirm=confirm, parent=parent)

    def _remove_current_state(self):
        self._state_manager.remove_current_state()

    def _save_state_settings(self):
        self._state_manager.save_state_settings()

    def _state_settings_to_dict(self, settings: StateSettings) -> dict:
        return self._state_manager.state_settings_to_dict(settings)

    def _state_settings_from_dict(self, key: str, data: dict) -> StateSettings:
        return self._state_manager.state_settings_from_dict(key, data)

    def _persist_state_definitions(self):
        self._state_manager.persist_state_definitions()

    def _state_storage_token(self, key: str) -> str:
        return self._state_manager._state_storage_token(key)

    def _state_storage_path_for_key(self, key: str) -> Path:
        return self._state_manager.state_storage_path_for_key(key)

    def _state_variants_dir_for_key(self, key: str) -> Path:
        return self._state_manager.state_variants_dir_for_key(key)

    def _move_storage_path_for_key(self, key: str) -> Path:
        return self._state_manager.move_storage_path_for_key(key)

    def _apply_move_gif_update(self, action_key: str):
        normalized = (action_key or "").strip().lower()
        if not normalized:
            return
        move_settings = self._move_state_defs.get(normalized)
        if move_settings is None:
            return
        target_path = self._move_storage_path_for_key(normalized)
        if not target_path.is_file():
            return
        try:
            resolved = str(target_path.resolve())
        except OSError:
            resolved = str(target_path)
        state_key = move_settings.state_key
        state_settings = self._state_defs.get(state_key)
        if state_settings:
            if state_settings.gif_path != resolved:
                state_settings.gif_path = resolved
            self._update_state_variants(state_key)
            if self._current_state_key == state_key and self._state_settings is not None:
                self._state_settings.gif_path = resolved
                self._active_gif_path = None
                self._apply_state_settings()
                self.update()
            # Persist gif path for the underlying state
            self._config.setValue(f"state/{state_key}/gif_path", resolved)
        self._write_state_list()
        self._write_move_state_list()
        if state_key == self._current_state_key:
            self._persist_current_state()
        else:
            self._persist_state_definitions()

    def _update_state_variants(self, key: str):
        settings = self._state_defs.get(key)
        if settings is None:
            return
        variants: list[str] = []
        primary = settings.gif_path
        if primary:
            try:
                primary_path = Path(primary)
                if primary_path.is_file():
                    variants.append(str(primary_path.resolve()))
            except OSError:
                pass
        variants_dir = self._state_variants_dir_for_key(key)
        if variants_dir.is_dir():
            for path in sorted(variants_dir.glob("*.gif")):
                try:
                    resolved = str(path.resolve())
                except OSError:
                    continue
                if resolved not in variants and Path(resolved).is_file():
                    variants.append(resolved)
        settings.gif_variants = variants

    def _ensure_local_gif_for_state(self, key: str):
        settings = self._state_defs.get(key)
        if settings is None:
            return
        if key == "walking":
            walking_source = self._move_storage_dir / "walking.gif"
            if walking_source.is_file():
                settings.gif_path = str(walking_source.resolve())
            elif self._default_idle_gif.is_file():
                # 如果沒有步行資源，就改用預設 idle 圖保持顯示
                settings.gif_path = str(self._default_idle_gif.resolve())
            else:
                settings.gif_path = None
            self._update_state_variants(key)
            return
        current_path = settings.gif_path
        assigned = False
        if current_path:
            src = Path(current_path)
            if src.is_file():
                dest = self._state_storage_path_for_key(key)
                try:
                    if src.resolve() == dest.resolve():
                        settings.gif_path = str(dest.resolve())
                        assigned = True
                except OSError:
                    pass
                try:
                    shutil.copy2(src, dest)
                except OSError:
                    pass
                else:
                    try:
                        settings.gif_path = str(dest.resolve())
                    except OSError:
                        settings.gif_path = str(dest)
                    assigned = True
        if not assigned:
            if self._default_idle_gif.is_file():
                try:
                    settings.gif_path = str(self._default_idle_gif.resolve())
                except OSError:
                    settings.gif_path = str(self._default_idle_gif)
            else:
                settings.gif_path = None
        self._update_state_variants(key)

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

    def show_chat_message(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        self._renderer.set_bubble_text(
            text,
            override_visibility=override_visibility,
            auto_hide=auto_hide,
            hide_delay_ms=hide_delay_ms,
        )

    _set_bubble_text = show_chat_message

    def clear_chat_message(self):
        self._renderer.clear_bubble_text()

    _clear_bubble_text = clear_chat_message

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
        self.set_busy_cursor(False)
        timer = getattr(self, "_companion_timer", None)
        if isinstance(timer, QtCore.QTimer):
            timer.stop()
        super().closeEvent(event)
    def restart_app(self):
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

    _restart_app = restart_app

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
