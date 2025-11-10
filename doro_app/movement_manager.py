"""Movement handling helper for the Doro window."""

from __future__ import annotations

import math
import time
from typing import Optional, TYPE_CHECKING

from PySide6 import QtCore

from .actions import MOVE_DIRECTIONS, MOVE_TOKEN_PATTERN
from .models import MoveStateSettings, MovementRequest
from .utils import safe_float as _safe_float, safe_int as _safe_int

if TYPE_CHECKING:
    from .window import DoroWindow


class MovementManager:
    """Encapsulates movement parsing, execution, and reporting."""

    def __init__(self, window: DoroWindow):
        self._window = window
        self._active_movement: MovementRequest | None = None
        self._movement_remaining = 0.0
        self._movement_velocity = QtCore.QPointF(0.0, 0.0)
        self._movement_start_pos = QtCore.QPoint()
        self._movement_direction_key: Optional[str] = None
        self._movement_pending_report: Optional[str] = None
        self._movement_previous_state: Optional[str] = None
        self._movement_reports: list[str] = []
        self._last_move_report = ""

    # ------------------------------------------------------------------ Public API

    def instruction_text(self) -> str:
        step = max(12, int(getattr(self._window, "_movement_step_px", 60)))
        return (
            "輸出格式提醒：\n"
            "  • 狀態請以括號標註，例如 (HAPPY) 文字內容。\n"
            "  • 移動指令請以方括號附在句尾，例如 [MOVE:dir=left;distance=80;speed=med]，"
            "若無需移動請輸出 [MOVE:NONE]。\n"
            f"  • distance 為像素距離（>0 依 direction 前進；可用 left/right/up/down/左/右/上/下 等），一次約 {step}px；"
            "speed 必須是 slow|med|fast。\n"
            "  • 仍支援舊版 dx、dy 參數，但優先使用方向 + distance + speed。\n"
            "請保持順暢的中文對話內容，括號與方括號僅供程式解析，不會顯示給使用者。"
        )

    def record_manual_report(self, report: str | None):
        if report:
            self._record_move_report(report)

    def parse_movement_token(self, token: str) -> tuple[int, int] | None:
        raw = token.strip()
        if not raw:
            return None
        match = MOVE_TOKEN_PATTERN.match(raw)
        if not match:
            return None
        direction = match.group(1)
        key = self._normalize_direction_key(direction)
        return MOVE_DIRECTIONS.get(key)

    def handle_move_bracket(self, token: str, reports: list[str]) -> bool:
        parsed = self._parse_move_bracket(token)
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

        window = self._window
        if action_lower in base_moves:
            dx_param = params.get("dx")
            dy_param = params.get("dy")
            direction_key = params.get("dir") or params.get("direction") or params.get("to") or params.get("向")
            distance_param = params.get("distance") or params.get("dist") or params.get("offset") or params.get("距離")
            speed_param = params.get("speed") or params.get("spd") or params.get("速度")
            state_hint = params.get("state") or params.get("狀態")
            move_state_param = (
                params.get("move_state")
                or params.get("move-state")
                or params.get("movestate")
                or params.get("移動狀態")
            )
            move_state_key, move_state_settings = window._resolve_move_state(move_state_param)
            if move_state_settings is None:
                move_state_key, move_state_settings = window._resolve_move_state(window._default_move_state_key)

            direction_vec = None
            if direction_key:
                direction_vec = self._direction_vector_from_string(direction_key)

            if direction_vec is None and (dx_param is not None or dy_param is not None):
                dx_val = float(_safe_int(dx_param, 0))
                dy_val = float(_safe_int(dy_param, 0))
                length = math.hypot(dx_val, dy_val)
                if length > 0.5:
                    direction_vec = (dx_val / length, dy_val / length)
                    distance_param = length

            if direction_vec is None:
                return True

            step_default = window._movement_step_px
            if distance_param not in (None, ""):
                distance_val = abs(float(_safe_float(distance_param, float(step_default))))
            elif move_state_settings and move_state_settings.default_distance is not None:
                distance_val = abs(float(move_state_settings.default_distance))
            else:
                distance_val = float(step_default)

            current = window.frameGeometry().topLeft()
            target_guess = QtCore.QPoint(
                round(current.x() + direction_vec[0] * distance_val),
                round(current.y() + direction_vec[1] * distance_val),
            )
            extra_dx = self._extra_dx(direction_vec)
            if extra_dx:
                target_guess.setX(target_guess.x() + extra_dx)
            target = window._clamp_window_position(target_guess)
            actual_dx = target.x() - current.x()
            actual_dy = target.y() - current.y()
            actual_distance = math.hypot(actual_dx, actual_dy)
            if actual_distance <= 0.5:
                return True

            direction_vector = (actual_dx / actual_distance, actual_dy / actual_distance)
            direction_label = self._direction_label(direction_vector)
            report = self._format_move_report(
                target,
                direction_label,
                int(round(actual_dx)),
                int(round(actual_dy)),
            )

            speed_source = speed_param or (
                move_state_settings.default_speed if move_state_settings else None
            ) or "med"
            speed_name = speed_source.lower()
            self._start_movement(
                direction_vector,
                actual_distance,
                speed_name=speed_name,
                state_hint=state_hint,
                report=report,
                move_state=move_state_settings,
                move_state_name=move_state_key,
            )
            return True

        if action_lower == "face":
            dir_hint = params.get("dir", "").strip().lower()
            bubble_offset = window._bubble_offset
            if dir_hint in ("left", "l", "左"):
                window._apply_bubble_offset(QtCore.QPointF(-abs(bubble_offset.x() or 120.0), bubble_offset.y()), persist=True)
            elif dir_hint in ("right", "r", "右"):
                window._apply_bubble_offset(QtCore.QPointF(abs(bubble_offset.x() or 120.0), bubble_offset.y()), persist=True)
            return True
        return True

    def process_active_movement(self, dt: float):
        if not self._active_movement or dt <= 0.0:
            return

        velocity = self._movement_velocity
        step_dx = velocity.x() * dt
        step_dy = velocity.y() * dt
        if step_dx == 0.0 and step_dy == 0.0:
            return

        window = self._window
        current_pos = window.frameGeometry().topLeft()
        desired = QtCore.QPoint(round(current_pos.x() + step_dx), round(current_pos.y() + step_dy))
        clamped = window._clamp_window_position(desired)
        actual_dx = clamped.x() - current_pos.x()
        actual_dy = clamped.y() - current_pos.y()
        window._move_window_to(clamped)

        moved_distance = math.hypot(actual_dx, actual_dy)
        remaining = self._movement_remaining - moved_distance
        if remaining <= 0.5 or moved_distance <= 0.01:
            self._finish_movement(final_position=clamped)
        else:
            self._movement_remaining = remaining

    def apply_directional_move(self, direction: tuple[int, int]) -> str | None:
        dx, dy = direction
        if dx == 0 and dy == 0:
            return None
        step = max(12, int(getattr(self._window, "_movement_step_px", 60)))
        current = self._window.frameGeometry().topLeft()
        target = QtCore.QPoint(round(current.x() + dx * step), round(current.y() + dy * step))
        extra_dx = self._extra_dx((dx, dy))
        if extra_dx:
            target.setX(target.x() + extra_dx)
        clamped = self._window._clamp_window_position(target)
        actual_dx = clamped.x() - current.x()
        actual_dy = clamped.y() - current.y()
        self._window._move_window_to(clamped)
        direction_vector = (actual_dx, actual_dy)
        direction_label = self._direction_label(direction_vector)
        return self._format_move_report(clamped, direction_label, actual_dx, actual_dy)

    # ------------------------------------------------------------------ Internals

    def _parse_move_bracket(self, token: str) -> tuple[str, dict[str, str]] | None:
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
            params[key.strip().lower()] = value.strip()

        return action_key, params

    def _direction_vector_from_string(self, value: str) -> tuple[int, int] | None:
        key = self._normalize_direction_key(value)
        vec = MOVE_DIRECTIONS.get(key)
        if vec:
            return vec
        if ";" in value:
            dx = None
            dy = None
            try:
                for part in value.split(";"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    if k.strip().lower() == "dx":
                        dx = float(v.strip())
                    elif k.strip().lower() == "dy":
                        dy = float(v.strip())
            except ValueError:
                return None
            if dx is not None and dy is not None:
                length = math.hypot(dx, dy)
                if length > 0:
                    return (dx / length, dy / length)
        return None

    def _finish_movement(self, final_position: QtCore.QPoint | None = None):
        if not self._active_movement:
            return
        window = self._window
        report = self._movement_pending_report
        if final_position is None:
            final_position = window.frameGeometry().topLeft()
        if report is None:
            direction_label = self._direction_label(self._active_movement.direction)
            report = self._format_move_report(final_position, direction_label, 0, 0)
        self._record_move_report(report)
        self._active_movement = None
        self._movement_velocity = QtCore.QPointF(0.0, 0.0)
        self._movement_remaining = 0.0
        self._movement_pending_report = None
        self._movement_direction_key = None
        if self._movement_previous_state and window._state_service.states.get(self._movement_previous_state):
            if window._current_state_key != self._movement_previous_state:
                window._state_service.set_state(self._movement_previous_state)
        self._movement_previous_state = None

    def _format_move_report(self, pos: QtCore.QPoint, direction_label: str | None, dx: int, dy: int) -> str:
        prefix = f"往{direction_label}" if direction_label else "移動"
        deltas = []
        if dx:
            deltas.append(f"dx={dx}")
        if dy:
            deltas.append(f"dy={dy}")
        delta_info = f" ({', '.join(deltas)})" if deltas else ""
        return f"{prefix}，位置 {pos.x()}, {pos.y()}{delta_info}"

    def _direction_label(self, direction: tuple[float, float]) -> str:
        dx, dy = direction
        key = (
            int(math.copysign(1, dx)) if abs(dx) > 0.2 else 0,
            int(math.copysign(1, dy)) if abs(dy) > 0.2 else 0,
        )
        mapping = {
            (-1, 0): "左",
            (1, 0): "右",
            (0, -1): "上",
            (0, 1): "下",
            (-1, -1): "左上",
            (1, -1): "右上",
            (-1, 1): "左下",
            (1, 1): "右下",
        }
        return mapping.get(key, "未知方向")

    def _direction_slug(self, direction: tuple[float, float]) -> Optional[str]:
        dx, dy = direction
        key = (
            int(math.copysign(1, dx)) if abs(dx) > 0.2 else 0,
            int(math.copysign(1, dy)) if abs(dy) > 0.2 else 0,
        )
        mapping = {
            (-1, 0): "left",
            (1, 0): "right",
            (0, -1): "up",
            (0, 1): "down",
            (-1, -1): "up_left",
            (1, -1): "up_right",
            (-1, 1): "down_left",
            (1, 1): "down_right",
        }
        return mapping.get(key)

    def _extra_dx(self, direction: tuple[float, float]) -> int:
        if not direction:
            return 0
        dx = direction[0]
        if abs(dx) < 0.01:
            return 0
        return 100 if dx > 0 else -100

    def _record_move_report(self, report: str):
        self._last_move_report = report
        self._movement_reports.append(report)
        if len(self._movement_reports) > 50:
            self._movement_reports = self._movement_reports[-50:]
        try:
            print(f"[doro move] {report}")
        except Exception:
            pass

    def _normalize_direction_key(self, value: str) -> str:
        key = (value or "").strip()
        if not key:
            return ""
        key = key.replace(" ", "").replace("_", "").replace("-", "")
        return key.lower() if key.isascii() else key

    def _start_movement(
        self,
        direction: tuple[float, float],
        distance: float,
        *,
        speed_name: str = "med",
        state_hint: Optional[str] = None,
        report: Optional[str] = None,
        move_state: MoveStateSettings | None = None,
        move_state_name: Optional[str] = None,
    ):
        window = self._window
        unit_x, unit_y = direction
        length = math.hypot(unit_x, unit_y)
        if length <= 0:
            return
        unit_x /= length
        unit_y /= length
        speed_value = self._resolve_speed_value(speed_name)
        velocity = QtCore.QPointF(unit_x * speed_value, unit_y * speed_value)
        self._movement_velocity = velocity
        self._movement_remaining = distance
        self._movement_start_pos = window.frameGeometry().topLeft()
        self._movement_direction_key = self._direction_slug(direction)
        self._movement_pending_report = report
        self._movement_previous_state = window._current_state_key
        window._last_tick_time = time.monotonic()
        self._set_movement_state(
            direction,
            speed_name,
            move_state=move_state,
            prefer_walking=move_state_name == window._default_move_state_key,
        )
        self._active_movement = MovementRequest(
            direction=direction,
            distance_px=distance,
            speed_px_per_s=speed_value,
            state_key=window._current_state_key,
            move_state=move_state_name,
        )

    def _set_movement_state(
        self,
        direction: tuple[float, float],
        speed_name: str,
        *,
        move_state: MoveStateSettings | None = None,
        prefer_walking: bool = False,
    ):
        window = self._window

        # Check if walking state exists
        walking_available = window._state_service.states.get("walking") is not None

        # Determine desired state for movement
        slug = self._direction_slug(direction)

        if move_state and window._state_service.states.get(move_state.state_key):
            desired_key = move_state.state_key
        else:
            # TODO: Implement pick_random_state_for_direction in StateService
            # For now, prefer walking or infer from movement
            if prefer_walking and walking_available:
                desired_key = "walking"
            else:
                desired_key = self._infer_state_for_movement(direction, speed_name)
                if not desired_key and walking_available:
                    desired_key = "walking"

        if desired_key and window._state_service.states.get(desired_key) and desired_key != window._current_state_key:
            window._state_service.set_state(desired_key)

    def _infer_state_for_movement(self, direction: tuple[float, float], speed_name: str) -> Optional[str]:
        window = self._window
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
            if window._state_service.states.get(key):
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
