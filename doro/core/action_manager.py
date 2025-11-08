from __future__ import annotations

import math
import time
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Optional

from PySide6 import QtCore, QtGui, QtWidgets


ACTION_TOKEN_PATTERN = re.compile(
    r"^(?:move|mv|walk|go|travel|shift|step|run|向|往|移動|走|行)[\s:_-]*([a-z]+|[上下左右]{1,2})$",
    re.IGNORECASE,
)
ACTION_DIRECTIONS: dict[str, tuple[int, int]] = {
    "left": (-1, 0),
    "l": (-1, 0),
    "west": (-1, 0),
    "right": (1, 0),
    "r": (1, 0),
    "east": (1, 0),
    "up": (0, -1),
    "u": (0, -1),
    "north": (0, -1),
    "down": (0, 1),
    "d": (0, 1),
    "south": (0, 1),
    "upleft": (-1, -1),
    "leftup": (-1, -1),
    "ul": (-1, -1),
    "up-left": (-1, -1),
    "left-up": (-1, -1),
    "upright": (1, -1),
    "rightup": (1, -1),
    "ur": (1, -1),
    "up-right": (1, -1),
    "right-up": (1, -1),
    "downleft": (-1, 1),
    "leftdown": (-1, 1),
    "dl": (-1, 1),
    "down-left": (-1, 1),
    "left-down": (-1, 1),
    "downright": (1, 1),
    "rightdown": (1, 1),
    "dr": (1, 1),
    "down-right": (1, 1),
    "right-down": (1, 1),
    "上": (0, -1),
    "下": (0, 1),
    "左": (-1, 0),
    "右": (1, 0),
    "上左": (-1, -1),
    "上右": (1, -1),
    "下左": (-1, 1),
    "下右": (1, 1),
    "左上": (-1, -1),
    "右上": (1, -1),
    "左下": (-1, 1),
    "右下": (1, 1),
}


class ActionRequest(NamedTuple):
    direction: tuple[float, float]
    distance_px: float
    speed_px_per_s: float
    state_key: Optional[str]
    action_state: Optional[str] = None


@dataclass
class ActionStateSettings:
    state_key: str
    direction: str = "any"
    default_distance: float | None = None
    default_speed: str | None = None


class ActionManagerMixin:
    """Encapsulates movement/action logic for Doro."""

    def _init_action_system(self):
        self._action_step_px = getattr(self, "_action_step_px", 60)
        self._default_action_state_key = getattr(self, "_default_action_state_key", "walking")
        if not hasattr(self, "_action_state_defs"):
            self._action_state_defs: dict[str, ActionStateSettings] = {}
        if not hasattr(self, "_action_only_state_keys"):
            self._action_only_state_keys: set[str] = {"walking"}
        self._action_state_list_text = ""
        self._action_reports: list[str] = []
        self._last_action_report: str = ""
        self._active_action: ActionRequest | None = None
        self._action_remaining = 0.0
        self._action_velocity = QtCore.QPointF(0.0, 0.0)
        self._action_start_pos = QtCore.QPoint()
        self._action_direction_key: Optional[str] = None
        self._pending_action_report: Optional[str] = None
        self._action_previous_state: Optional[str] = None
        self._init_action_states()

    # --- Parsing --------------------------------------------------------
    def _parse_action_token(self, token: str) -> tuple[int, int] | None:
        raw = token.strip()
        if not raw:
            return None
        match = ACTION_TOKEN_PATTERN.match(raw)
        if not match:
            return None
        direction = match.group(1)
        key = self._normalize_direction_key(direction)
        return ACTION_DIRECTIONS.get(key)

    def _handle_action_bracket(self, token: str, reports: list[str]) -> bool:
        parsed = self._parse_action_bracket(token)
        if not parsed:
            return False
        action, params = parsed
        action_lower = action.lower()
        if action_lower in ("none", "stay", "idle", "停", "不動"):
            return True
        base_moves = {"", "move", "walk", "slide", "step"}
        if action_lower and action_lower not in base_moves and action_lower not in {"face", "none", "stay", "idle", "停", "不動"}:
            if params.get("dir") is None:
                params["dir"] = action_lower
            action_lower = "move"

        if action_lower in base_moves:
            dx_param = params.get("dx")
            dy_param = params.get("dy")
            direction_key = (
                params.get("dir")
                or params.get("direction")
                or params.get("to")
                or params.get("向")
            )
            distance_param = (
                params.get("distance")
                or params.get("dist")
                or params.get("offset")
                or params.get("距離")
            )
            speed_param = params.get("speed") or params.get("spd") or params.get("速度")
            state_hint = params.get("state") or params.get("狀態")
            action_state_param = (
                params.get("action_state")
                or params.get("action-state")
                or params.get("actionstate")
                or params.get("move_state")
                or params.get("move-state")
                or params.get("movestate")
                or params.get("動作狀態")
                or params.get("移動狀態")
            )
            action_state_key, action_state_settings = self._resolve_action_state(action_state_param)
            if action_state_settings is None:
                action_state_key, action_state_settings = self._resolve_action_state(self._default_action_state_key)

            direction_vec = None
            if direction_key:
                direction_vec = self._direction_vector_from_string(direction_key)

            if direction_vec is None and (dx_param is not None or dy_param is not None):
                dx_val = float(self._safe_int(dx_param, 0))
                dy_val = float(self._safe_int(dy_param, 0))
                length = math.hypot(dx_val, dy_val)
                if length > 0.5:
                    direction_vec = (dx_val / length, dy_val / length)
                    distance_param = length

            if direction_vec is None:
                return True

            step_default = self._action_step_px
            if distance_param not in (None, ""):
                distance_val = abs(float(self._safe_float(distance_param, float(step_default))))
            elif action_state_settings and action_state_settings.default_distance is not None:
                distance_val = abs(float(action_state_settings.default_distance))
            else:
                distance_val = float(step_default)

            current = self.frameGeometry().topLeft()
            target_guess = QtCore.QPoint(
                round(current.x() + direction_vec[0] * distance_val),
                round(current.y() + direction_vec[1] * distance_val),
            )
            target = self._clamp_window_position(target_guess)
            actual_dx = target.x() - current.x()
            actual_dy = target.y() - current.y()
            actual_distance = math.hypot(actual_dx, actual_dy)
            if actual_distance <= 0.5:
                return True

            direction_vector = (actual_dx / actual_distance, actual_dy / actual_distance)
            direction_label = self._direction_label(direction_vector)
            report = self._format_action_report(
                target,
                direction_label,
                int(round(actual_dx)),
                int(round(actual_dy)),
            )

            speed_source = speed_param or (
                action_state_settings.default_speed if action_state_settings else None
            ) or "med"
            speed_name = speed_source.lower()
            self._start_action(
                direction_vector,
                actual_distance,
                speed_name=speed_name,
                state_hint=state_hint,
                report=report,
                action_state=action_state_settings,
                action_state_name=action_state_key,
            )
            return True

        if action_lower == "face":
            dir_hint = params.get("dir", "").strip().lower()
            bubble = getattr(self, "_bubble", None)
            current_offset = bubble.offset if bubble else QtCore.QPointF(120.0, -110.0)
            offset_y = current_offset.y()
            base_x = abs(current_offset.x() or 120.0)
            if dir_hint in ("left", "l", "左"):
                self._apply_bubble_offset(QtCore.QPointF(-base_x, offset_y), persist=True)
            elif dir_hint in ("right", "r", "右"):
                self._apply_bubble_offset(QtCore.QPointF(base_x, offset_y), persist=True)
            return True
        return True

    def _parse_action_bracket(self, token: str) -> tuple[str, dict[str, str]] | None:
        parts = [part.strip() for part in token.split(";") if part.strip()]
        if not parts:
            return None
        header = parts[0]
        prefix = header
        action_part = ""
        if ":" in header:
            prefix, action_part = header.split(":", 1)
        if prefix.strip().lower() != "move":
            return None
        action_key = ""
        params: dict[str, str] = {}
        param_candidates: list[str] = []

        action_part = action_part.strip()
        if action_part:
            if "=" in action_part:
                param_candidates.append(action_part)
            else:
                action_key = action_part

        for part in parts[1:]:
            if "=" not in part:
                continue
            param_candidates.append(part)

        for part in param_candidates:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()

        if not action_key and params.get("dir"):
            action_key = "move"
        return action_key or "move", params

    # --- Movement helpers ----------------------------------------------
    def _apply_pixel_move(self, dx: int, dy: int) -> str | None:
        if dx == 0 and dy == 0:
            return None
        current = self.frameGeometry().topLeft()
        desired = QtCore.QPoint(current.x() + dx, current.y() + dy)
        clamped = self._clamp_window_position(desired)
        self._move_window_to(clamped)
        label = self._derive_direction_from_delta(dx, dy)
        return self._format_action_report(clamped, label, dx, dy)

    def _apply_directional_move(self, direction: tuple[int, int]) -> str | None:
        dx, dy = direction
        if dx == 0 and dy == 0:
            return None
        step = max(12, int(self._action_step_px))
        current = self.frameGeometry().topLeft()
        target = QtCore.QPoint(round(current.x() + dx * step), round(current.y() + dy * step))
        clamped = self._clamp_window_position(target)
        actual_dx = clamped.x() - current.x()
        actual_dy = clamped.y() - current.y()
        actual_distance = math.hypot(actual_dx, actual_dy)
        if actual_distance <= 0.5:
            return None
        direction_vector = (actual_dx / actual_distance, actual_dy / actual_distance)
        direction_label = self._direction_label(direction_vector)
        report = self._format_action_report(
            clamped,
            direction_label,
            int(round(actual_dx)),
            int(round(actual_dy)),
        )
        action_state_key, action_state_settings = self._resolve_action_state(self._default_action_state_key)
        self._start_action(
            direction_vector,
            actual_distance,
            speed_name="med",
            report=report,
            action_state=action_state_settings,
            action_state_name=action_state_key,
        )
        return None

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

    # --- Action processing ----------------------------------------------
    def _process_active_action(self, dt: float):
        if not self._active_action or dt <= 0.0:
            return

        velocity = self._action_velocity
        step_dx = velocity.x() * dt
        step_dy = velocity.y() * dt
        if step_dx == 0.0 and step_dy == 0.0:
            return

        current_pos = self.frameGeometry().topLeft()
        desired = QtCore.QPoint(round(current_pos.x() + step_dx), round(current_pos.y() + step_dy))
        clamped = self._clamp_window_position(desired)
        actual_dx = clamped.x() - current_pos.x()
        actual_dy = clamped.y() - current_pos.y()
        self._move_window_to(clamped)

        moved_distance = math.hypot(actual_dx, actual_dy)
        remaining = self._action_remaining - moved_distance
        if remaining <= 0.5 or moved_distance <= 0.01:
            self._finish_action(final_position=clamped)
        else:
            self._action_remaining = remaining

    def _finish_action(self, final_position: QtCore.QPoint | None = None):
        if not self._active_action:
            return
        report = self._pending_action_report
        if final_position is None:
            final_position = self.frameGeometry().topLeft()
        if report is None:
            direction_label = self._direction_label(self._active_action.direction)
            report = self._format_action_report(final_position, direction_label, 0, 0)
        self._record_action_report(report)
        self._active_action = None
        self._action_velocity = QtCore.QPointF(0.0, 0.0)
        self._action_remaining = 0.0
        self._pending_action_report = None
        self._action_direction_key = None
        if self._action_previous_state and self._action_previous_state in self._state_defs:
            if self._current_state_key != self._action_previous_state:
                self._set_state(self._action_previous_state)
        self._action_previous_state = None

    def _format_action_report(self, pos: QtCore.QPoint, direction_label: str | None, dx: int, dy: int) -> str:
        prefix = f"往{direction_label}執行動作" if direction_label else "執行動作"
        deltas = []
        if dx:
            deltas.append(f"dx={dx}")
        if dy:
            deltas.append(f"dy={dy}")
        delta_info = f" ({', '.join(deltas)})" if deltas else ""
        return f"{prefix}，位置 {pos.x()}, {pos.y()}{delta_info}"

    def _record_action_report(self, report: str):
        self._last_action_report = report
        self._action_reports.append(report)
        if len(self._action_reports) > 50:
            self._action_reports = self._action_reports[-50:]
        try:
            print(f"[doro action] {report}")
        except Exception:
            pass

    # --- Action execution -----------------------------------------------
    def _start_action(
        self,
        direction: tuple[float, float],
        distance: float,
        *,
        speed_name: str = "med",
        state_hint: Optional[str] = None,
        report: Optional[str] = None,
        action_state: ActionStateSettings | None = None,
        action_state_name: Optional[str] = None,
    ) -> bool:
        unit_x, unit_y = direction
        length = math.hypot(unit_x, unit_y)
        if length <= 1e-6:
            return False
        unit_x /= length
        unit_y /= length
        distance = max(0.0, float(distance))
        if distance <= 0.5:
            if report:
                self._record_action_report(report)
            return False

        if self._active_action:
            self._finish_action()

        speed_px_per_s = self._resolve_speed_value(speed_name)
        velocity = QtCore.QPointF(unit_x * speed_px_per_s, unit_y * speed_px_per_s)

        walking_available, walking_added = self._ensure_walking_state_available()
        if walking_added:
            self._write_state_list()

        action_state_key = None
        if action_state and action_state.state_key in self._state_defs:
            action_state_key = action_state.state_key
        elif walking_available:
            action_state_key = "walking"

        self._active_action = ActionRequest(
            direction=(unit_x, unit_y),
            distance_px=distance,
            speed_px_per_s=speed_px_per_s,
            state_key=action_state_key,
            action_state=action_state_name,
        )
        self._action_velocity = velocity
        self._action_remaining = distance
        self._action_start_pos = self.frameGeometry().topLeft()
        self._action_direction_key = self._direction_slug(direction)
        self._pending_action_report = report
        self._last_tick_time = time.monotonic()
        self._action_previous_state = self._current_state_key
        self._set_action_state(
            direction,
            speed_name,
            action_state=action_state,
            prefer_walking=walking_available,
        )
        return True

    def _set_action_state(
        self,
        direction: tuple[float, float],
        speed_name: str,
        *,
        action_state: ActionStateSettings | None = None,
        prefer_walking: bool = False,
    ):
        walking_available, walking_added = self._ensure_walking_state_available()
        if walking_added:
            self._write_state_list()
        if action_state and action_state.state_key in self._state_defs:
            desired_key = action_state.state_key
        else:
            should_use_walking = prefer_walking or walking_available
            if should_use_walking and "walking" in self._state_defs:
                desired_key = "walking"
            else:
                desired_key = self._infer_state_for_action(direction, speed_name)
        if desired_key and desired_key in self._state_defs and desired_key != self._current_state_key:
            self._set_state(desired_key)

    def _infer_state_for_action(self, direction: tuple[float, float], speed_name: str) -> Optional[str]:
        slug = self._direction_slug(direction)
        if not slug:
            return None
        candidates = [
            f"walk_{slug}_{speed_name}",
            f"walk_{slug}",
            f"move_{slug}_{speed_name}",
            f"move_{slug}",
            f"walk_{speed_name}",
            f"move_{speed_name}",
        ]
        for key in candidates:
            if key in self._state_defs:
                return key
        return None

    def _resolve_speed_value(self, speed_name: str) -> float:
        lookup = {
            "slow": 80.0,
            "med": 140.0,
            "medium": 140.0,
            "fast": 220.0,
        }
        return lookup.get(speed_name.lower(), 140.0)

    def _action_instruction_text(self) -> str:
        step = max(12, int(self._action_step_px))
        return (
            "輸出格式提醒：\n"
            "  • 狀態請以括號標註，例如 (HAPPY) 文字內容。\n"
            "  • 動作指令請以方括號附在句尾，例如 [MOVE:dir=left;distance=80;speed=med]，若無需動作請輸出 [MOVE:NONE]。\n"
            f"  • distance 為像素距離（>0 依 direction 前進；可用 left/right/up/down/左/右/上/下 等），一次約 {step}px；speed 必須是 slow|med|fast。\n"
            "  • 仍支援舊版 dx、dy 參數，但優先使用方向 + distance + speed。\n"
            "請保持輕鬆的中文對話內容，括號與方括號僅供程式解析，不會顯示給使用者。"
        )

    # --- Action state registry -----------------------------------------
    def _init_action_states(self):
        self._action_state_defs.clear()
        step_default = max(12, int(self._action_step_px))
        default_distance = float(step_default)
        default_speed = "med"
        self._register_action_state(
            self._default_action_state_key,
            state_key=self._default_action_state_key,
            default_distance=default_distance,
            default_speed=default_speed,
        )
        self._ensure_walking_state_available()

    def _register_action_state(
        self,
        key: str,
        *,
        state_key: str,
        direction: str | None = None,
        default_distance: float | None = None,
        default_speed: str | None = None,
    ):
        normalized = (key or "").strip().lower()
        if not normalized:
            return
        existing = self._action_state_defs.get(normalized)
        distance = (
            default_distance
            if default_distance is not None
            else (existing.default_distance if existing else None)
        )
        speed = (
            default_speed
            if default_speed is not None
            else (existing.default_speed if existing else None)
        )
        if direction is None and existing is not None:
            direction_value = existing.direction
        else:
            direction_value = (direction or "any").strip().lower() or "any"
        state_key_clean = (state_key or normalized).strip()
        if not state_key_clean:
            state_key_clean = normalized
        if state_key_clean:
            self._action_only_state_keys.add(state_key_clean.lower())
        new_settings = ActionStateSettings(
            state_key=state_key_clean,
            direction=direction_value,
            default_distance=distance,
            default_speed=speed,
        )
        changed = existing != new_settings
        self._action_state_defs[normalized] = new_settings
        return changed

    def _resolve_action_state(self, key: str | None) -> tuple[Optional[str], Optional[ActionStateSettings]]:
        if not key:
            return (None, None)
        normalized = key.strip().lower()
        if not normalized:
            return (None, None)
        settings = self._action_state_defs.get(normalized)
        if settings is None:
            return (None, None)
        return (normalized, settings)

    def _ensure_walking_state_available(self) -> tuple[bool, bool]:
        walking_key = "walking"
        step_default = max(12, int(self._action_step_px))
        action_state_updated = self._register_action_state(
            walking_key,
            state_key=walking_key,
            direction="any",
            default_distance=float(step_default),
            default_speed="med",
        )
        walking_path = self._action_storage_dir / f"{walking_key}.gif"
        state_changed = False
        if not walking_path.is_file():
            if action_state_updated:
                self._write_action_state_list()
            walking_settings = self._state_defs.get(walking_key)
            if walking_settings:
                walking_settings.gif_variants = []
            return False, False
        path_str = str(walking_path.resolve())
        added = False
        settings = self._state_defs.get(walking_key)
        if settings is None:
            settings = self._state_settings_from_dict(
                walking_key,
                {"label": "Walking"},
            )
            settings.gif_path = path_str
            self._state_defs[walking_key] = settings
            self._protected_state_keys.add(walking_key)
            added = True
            state_changed = True
        else:
            if settings.gif_path != path_str:
                settings.gif_path = path_str
                state_changed = True
        if state_changed or action_state_updated:
            self._write_action_state_list()
        self._update_state_variants(walking_key)
        return True, added

    def _show_action_gif_manager(self):
        self._ensure_walking_state_available()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Action GIFs")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet("#actionGifDialog { background-color: #060b15; border-radius: 18px; }")
        dialog.setObjectName("actionGifDialog")

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QtWidgets.QLabel("管理每個動作狀態所對應的 GIF。")
        header.setStyleSheet("color: #e5edff; font-weight: 600;")
        layout.addWidget(header)

        content = QtWidgets.QHBoxLayout()
        content.setSpacing(12)
        layout.addLayout(content, stretch=1)

        list_widget = QtWidgets.QListWidget(dialog)
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        list_widget.setStyleSheet(
            "QListWidget { background-color: rgba(15, 23, 42, 0.55); border-radius: 12px; padding: 8px; }"
            "QListWidget::item { color: #e2e8f0; padding: 6px 10px; border-radius: 8px; }"
            "QListWidget::item:selected { background-color: rgba(129, 140, 248, 0.35); }"
        )
        content.addWidget(list_widget, stretch=1)

        preview_label = QtWidgets.QLabel()
        preview_label.setFixedSize(200, 200)
        preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet(
            "background: rgba(15, 23, 42, 0.45); border-radius: 16px; color: #94a3b8; border: 1px solid rgba(148,163,184,0.25);"
        )
        content.addWidget(preview_label, stretch=1)

        preview_movie: list[QtGui.QMovie | None] = [None]

        def stop_preview():
            movie = preview_movie[0]
            if movie:
                movie.stop()
            preview_movie[0] = None
            preview_label.setMovie(None)

        def show_preview(path: Path | None):
            stop_preview()
            if not path or not path.is_file():
                preview_label.setText("尚未設定 GIF")
                return
            movie = QtGui.QMovie(str(path))
            if not movie.isValid():
                preview_label.setText("GIF 無法讀取")
                return
            movie.setScaledSize(QtCore.QSize(180, 180))
            preview_label.setMovie(movie)
            movie.start()
            preview_movie[0] = movie

        def current_action_key() -> str | None:
            item = list_widget.currentItem()
            if not item:
                return None
            return item.data(QtCore.Qt.ItemDataRole.UserRole)

        def repopulate(select_key: str | None = None):
            list_widget.clear()
            for key in sorted(self._action_state_defs.keys()):
                action_settings = self._action_state_defs[key]
                state_key = action_settings.state_key
                state_settings = self._state_defs.get(state_key)
                label = state_settings.label if state_settings else state_key
                direction = (action_settings.direction or "any").strip() or "any"
                item = QtWidgets.QListWidgetItem(f"{key}  →  {label} ({direction})")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, key)
                list_widget.addItem(item)
                if select_key and key == select_key:
                    item.setSelected(True)
            if not list_widget.count():
                preview_label.setText("尚未註冊任何動作狀態")
                return
            if not list_widget.selectedItems():
                list_widget.setCurrentRow(0)
            key = current_action_key()
            if key:
                show_preview(self._action_storage_path_for_key(key))

        def assign_gif():
            key = current_action_key()
            if not key:
                return
            dest = self._action_storage_path_for_key(key)
            start_dir = dest.parent if dest.parent.is_dir() else self._action_storage_dir
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog,
                f"Select GIF for '{key}'",
                str(start_dir),
                "GIF files (*.gif)",
            )
            if not file_path:
                return
            src = Path(file_path)
            if not src.is_file():
                QtWidgets.QMessageBox.warning(dialog, "Assign action GIF", "The selected file does not exist.")
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not dest.is_file() or src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
            except OSError as exc:
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Assign action GIF",
                    f"Failed to copy GIF into action storage:\n{exc}",
                )
                return
            if not dest.is_file():
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Assign action GIF",
                    "Failed to prepare the action GIF in the action folder.",
                )
                return
            self._apply_action_gif_update(key)
            repopulate(select_key=key)

        def reveal_folder():
            key = current_action_key()
            if not key:
                return
            path = self._action_storage_path_for_key(key)
            target = path if path.is_dir() else path.parent
            if not target.exists():
                target = self._action_storage_dir
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))

        def on_selection_changed():
            key = current_action_key()
            if key:
                show_preview(self._action_storage_path_for_key(key))

        list_widget.currentItemChanged.connect(lambda _curr, _prev: on_selection_changed())

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(10)
        layout.addLayout(button_row)

        assign_button = QtWidgets.QPushButton("指定 GIF…")
        assign_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        assign_button.clicked.connect(assign_gif)
        button_row.addWidget(assign_button)

        reveal_button = QtWidgets.QPushButton("開啟資料夾")
        reveal_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        reveal_button.clicked.connect(reveal_folder)
        button_row.addWidget(reveal_button)

        button_row.addStretch(1)

        close_button = QtWidgets.QPushButton("關閉")
        close_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        close_button.clicked.connect(dialog.close)
        button_row.addWidget(close_button)

        repopulate()
        dialog.finished.connect(lambda _code: stop_preview())
        dialog.exec()

    # --- Utility hooks --------------------------------------------------
    @staticmethod
    def _safe_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = [
    "ACTION_DIRECTIONS",
    "ACTION_TOKEN_PATTERN",
    "ActionManagerMixin",
    "ActionRequest",
    "ActionStateSettings",
]
