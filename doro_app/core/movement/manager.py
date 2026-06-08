"""Movement handling helper for the Doro window."""

from __future__ import annotations

import time
import math
from typing import Callable, Optional, TYPE_CHECKING

from PySide6 import QtCore

from ...utils.actions import MOVE_DIRECTIONS, MOVE_TOKEN_PATTERN
from ...utils.models import MoveStateSettings, MovementRequest
from ...utils.paths import MOVEMENT_INSTRUCTION_PATH
from ...utils.prompts import load_prompt_text
from ...utils.utils import safe_float as _safe_float, safe_int as _safe_int
from .parser import (
    direction_label,
    direction_vector_from_string,
    direction_key,
    format_move_report,
    normalize_direction_key,
    parse_move_bracket,
)
from .repository import MovementRepository

if TYPE_CHECKING:
    from .port import MovementWindowPort
    from ..state import StateService


# Movement history size limit
MAX_MOVE_REPORTS = 50


class MovementManager:
    """Encapsulates movement parsing, execution, and reporting."""

    def __init__(
        self,
        window: "MovementWindowPort",
        state_service: StateService,
        movement_repo: MovementRepository,
    ):
        self._window = window
        self._state_service = state_service
        self._repo = movement_repo
        self._movement_step_px = movement_repo.defaults.step_px
        self._active_movement: MovementRequest | None = None
        self._movement_remaining = 0.0
        self._movement_velocity = QtCore.QPointF(0.0, 0.0)
        self._movement_start_pos = QtCore.QPoint()
        # Floating-point integrator for the window top-left during a walk.
        # Decouples the per-tick step from integer screen coordinates so
        # shallow-angle diagonals don't lose the sub-pixel axis to rounding.
        self._movement_fpos = QtCore.QPointF(0.0, 0.0)
        # Pre-computed clamped destination so the final frame can snap exactly
        # to the requested target instead of stopping wherever rounding lands.
        self._movement_target = QtCore.QPoint()
        self._movement_direction_key: Optional[str] = None
        self._movement_pending_report: Optional[str] = None
        self._movement_previous_state: Optional[str] = None
        self._movement_reports: list[str] = []
        self._last_move_report = ""
        self._last_error: Optional[str] = None  # Track last parse error
        # Physical-pixel target of the most recent successful `[move:to;x=;y=]`.
        # The click warning overlay reads this at wind-up time to frame the
        # a11y element Doro is walking towards (the foot hasn't arrived yet
        # when wind-up starts, so sampling the current foot position would
        # frame the wrong element).
        self.last_target_physical: Optional[tuple[int, int]] = None
        # Completion listeners: invoked exactly once per `_finish_movement` call.
        # Used by `MovementAction` (see core/action/movement_action.py) so the
        # dispatcher can sequence the next action without polling. Listeners
        # are also fired when `cancel_active_movement` ends a movement early
        # so waiters don't strand.
        self._completion_listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ Public API

    @property
    def has_active_movement(self) -> bool:
        return self._active_movement is not None

    def add_completion_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register *callback* to fire after the next movement finishes.

        Returns an `unsubscribe` callable so the caller can detach without
        knowing the registration index (matches the WaitPhase contract used by
        `MovementAction`). Listeners persist across movements until they
        unsubscribe — typical usage subscribes per-action and unsubs on the
        first fire.
        """
        self._completion_listeners.append(callback)

        def _unsubscribe() -> None:
            try:
                self._completion_listeners.remove(callback)
            except ValueError:
                pass

        return _unsubscribe

    def cancel_active_movement(self) -> bool:
        """Abort any in-flight movement, restoring the previous state.

        Returns True iff a movement was actually running. Notifies all
        completion listeners so action queue waiters unwind cleanly.
        Idempotent — calling with no active movement is a no-op.
        """
        if self._active_movement is None:
            return False
        self._finish_movement()
        return True

    def get_last_error(self) -> Optional[str]:
        """Get the last movement parsing error, if any."""
        return self._last_error

    def clear_error(self):
        """Clear the last error."""
        self._last_error = None

    def instruction_text(self) -> str:
        """Load movement instruction text from file and replace {{STEP}} placeholder."""
        step = max(12, self._movement_step_px)
        template = load_prompt_text(MOVEMENT_INSTRUCTION_PATH)
        return template.replace("{{STEP}}", str(step))

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
        key = normalize_direction_key(direction)
        return MOVE_DIRECTIONS.get(key)

    def handle_move_bracket(self, token: str, reports: list[str]) -> bool:
        parsed = parse_move_bracket(token)
        if not parsed:
            return False
        action, params = parsed
        action_lower = action.lower()
        if action_lower in ("none", "stay", "idle", "停", "不動"):
            return True

        # Phase 1c: absolute-target form `[move:to;x=X;y=Y]` — walk Doro to an
        # absolute screen coordinate using the existing walking animation.
        # Negative coordinates are rejected; out-of-screen coordinates are
        # clamped (same behavior as the directional form).
        if action_lower in ("to", "goto"):
            return self._handle_target_move(params, reports)

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
            move_state_key, move_state_settings = self._resolve_move_state_settings(move_state_param)
            if move_state_settings is None:
                default_key = self._state_service.get_default_movement_state()
                move_state_key, move_state_settings = self._resolve_move_state_settings(default_key)

            direction_vec = None
            if direction_key:
                direction_vec = direction_vector_from_string(direction_key)

            if direction_vec is None and (dx_param is not None or dy_param is not None):
                dx_val = float(_safe_int(dx_param, 0))
                dy_val = float(_safe_int(dy_param, 0))
                length = math.hypot(dx_val, dy_val)
                if length > 0.5:
                    direction_vec = (dx_val / length, dy_val / length)
                    distance_param = length

            if direction_vec is None:
                # Failed to parse direction - report error
                self._last_error = f"無法解析移動方向：dir={direction_key}, dx={dx_param}, dy={dy_param}"
                reports.append(f"[移動錯誤] {self._last_error}")
                return False

            step_default = self._movement_step_px
            if distance_param not in (None, ""):
                distance_val = abs(float(_safe_float(distance_param, float(step_default))))
            elif move_state_settings and move_state_settings.default_distance is not None:
                distance_val = abs(float(move_state_settings.default_distance))
            else:
                distance_val = float(step_default)

            current = window.current_position()
            target_guess = QtCore.QPoint(
                round(current.x() + direction_vec[0] * distance_val),
                round(current.y() + direction_vec[1] * distance_val),
            )
            target = window.clamp_window_position(target_guess)
            actual_dx = target.x() - current.x()
            actual_dy = target.y() - current.y()
            actual_distance = math.hypot(actual_dx, actual_dy)
            if actual_distance <= self._repo.defaults.completion_threshold:
                return True

            direction_vector = (actual_dx / actual_distance, actual_dy / actual_distance)
            direction_label_text = direction_label(direction_vector)
            report = format_move_report(
                target,
                direction_label_text,
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
            bubble_offset = window.get_bubble_offset()
            if dir_hint in ("left", "l", "左"):
                window.apply_bubble_offset(QtCore.QPointF(-abs(bubble_offset.x() or 120.0), bubble_offset.y()), persist=True)
            elif dir_hint in ("right", "r", "右"):
                window.apply_bubble_offset(QtCore.QPointF(abs(bubble_offset.x() or 120.0), bubble_offset.y()), persist=True)
            return True
        return True

    def process_active_movement(self, dt: float):
        if not self._active_movement or dt <= 0.0:
            return

        velocity = self._movement_velocity
        step_dx = velocity.x() * dt
        step_dy = velocity.y() * dt
        step_len = math.hypot(step_dx, step_dy)
        if step_len == 0.0:
            return

        window = self._window
        # This step would reach or overshoot the destination — snap to the
        # pre-computed target so we land on the exact requested pixel.
        if step_len >= self._movement_remaining:
            window.move_window_to(self._movement_target)
            self._finish_movement(final_position=self._movement_target)
            return

        # Integrate in floating point so sub-pixel components survive between
        # frames. We only round when actually moving the window.
        self._movement_fpos = QtCore.QPointF(
            self._movement_fpos.x() + step_dx,
            self._movement_fpos.y() + step_dy,
        )
        desired = self._movement_fpos.toPoint()
        clamped = window.clamp_window_position(desired)
        window.move_window_to(clamped)
        if clamped != desired:
            # Hit a screen-edge clamp — can't progress further along this
            # vector, finish in place rather than dragging on against the wall.
            self._finish_movement(final_position=clamped)
            return

        self._movement_remaining -= step_len
        if self._movement_remaining <= self._repo.defaults.completion_threshold:
            window.move_window_to(self._movement_target)
            self._finish_movement(final_position=self._movement_target)

    def _handle_target_move(self, params: dict, reports: list) -> bool:
        """Handle `[move:to;x=X;y=Y]` — walk Doro to a target.

        Returns True when the bracket is consumed (even on validation
        failure — the caller already matched action=='to' and should not
        fall through to other parsers). Errors are appended to `reports`.
        """
        x_raw = params.get("x")
        y_raw = params.get("y")
        if x_raw is None or y_raw is None:
            self._last_error = f"move:to 需要 x 與 y 參數 (got x={x_raw!r}, y={y_raw!r})"
            reports.append(f"[移動錯誤] {self._last_error}")
            return True

        try:
            target_x = int(float(x_raw))
            target_y = int(float(y_raw))
        except (TypeError, ValueError):
            self._last_error = f"move:to 的 x/y 必須為數字 (got x={x_raw!r}, y={y_raw!r})"
            reports.append(f"[移動錯誤] {self._last_error}")
            return True

        if target_x < 0 or target_y < 0:
            self._last_error = f"move:to 的 x/y 不可為負 (got {target_x},{target_y})"
            reports.append(f"[移動錯誤] {self._last_error}")
            return True

        self.last_target_physical = (target_x, target_y)
        window = self._window
        current = window.current_position()
        # (x, y) is where Doro's *sprite foot* should land, in *physical*
        # pixels — same anchor a11y elements / [mouse:click] / the warning
        # frame all use. Convert to logical, then back out the window
        # top-left from the sprite-foot offset (NOT frame centre/bottom —
        # SPRITE_OFFSET_X + panel reserve push the sprite far from the
        # window's geometric centre).
        foot_logical = window.logical_point_for_physical(target_x, target_y)
        foot_offset = window.sprite_foot_offset_logical()
        top_left = QtCore.QPoint(
            foot_logical.x() - foot_offset.x(),
            foot_logical.y() - foot_offset.y(),
        )
        clamped = window.clamp_window_position(top_left)
        actual_dx = clamped.x() - current.x()
        actual_dy = clamped.y() - current.y()
        actual_distance = math.hypot(actual_dx, actual_dy)
        if actual_distance <= self._repo.defaults.completion_threshold:
            # Already at (or essentially at) the target — nothing to animate.
            return True

        direction_vector = (actual_dx / actual_distance, actual_dy / actual_distance)
        direction_label_text = direction_label(direction_vector)
        report = format_move_report(
            clamped,
            direction_label_text,
            int(round(actual_dx)),
            int(round(actual_dy)),
        )

        speed_param = params.get("speed") or params.get("spd") or params.get("速度") or "med"
        move_state_key = self._state_service.get_default_movement_state()
        _, move_state_settings = self._resolve_move_state_settings(move_state_key)

        self._start_movement(
            direction_vector,
            actual_distance,
            speed_name=str(speed_param).lower(),
            state_hint=None,
            report=report,
            move_state=move_state_settings,
            move_state_name=move_state_key,
        )
        return True

    def apply_target_move(self, target_x: int, target_y: int) -> str | None:
        """Programmatic equivalent of `[move:to;x=...;y=...]`.

        Returns the resulting move report (also stored in history), or None
        if Doro is already at the target.
        """
        reports: list[str] = []
        self._handle_target_move({"x": target_x, "y": target_y}, reports)
        return reports[0] if reports else self._movement_pending_report

    def apply_directional_move(self, direction: tuple[int, int]) -> str | None:
        dx, dy = direction
        if dx == 0 and dy == 0:
            return None
        step = max(12, self._movement_step_px)
        current = self._window.current_position()
        target = QtCore.QPoint(round(current.x() + dx * step), round(current.y() + dy * step))
        clamped = self._window.clamp_window_position(target)
        actual_dx = clamped.x() - current.x()
        actual_dy = clamped.y() - current.y()
        self._window.move_window_to(clamped)
        direction_vector = (actual_dx, actual_dy)
        direction_label_text = direction_label(direction_vector)
        return format_move_report(clamped, direction_label_text, actual_dx, actual_dy)

    # ------------------------------------------------------------------ Internals

    def _finish_movement(self, final_position: QtCore.QPoint | None = None):
        if not self._active_movement:
            return
        window = self._window
        # Caller-supplied final_position marks the completion path (vs cancel,
        # which passes None). Only the completion path snaps the window back
        # after state revert — cancellation should leave Doro wherever she was
        # dragged to.
        snap_target = final_position
        report = self._movement_pending_report
        if final_position is None:
            final_position = window.current_position()
        if report is None:
            direction_label_text = direction_label(self._active_movement.direction)
            report = format_move_report(final_position, direction_label_text, 0, 0)
        self._record_move_report(report)
        self._active_movement = None
        self._movement_velocity = QtCore.QPointF(0.0, 0.0)
        self._movement_remaining = 0.0
        self._movement_pending_report = None
        self._movement_direction_key = None
        if self._movement_previous_state and self._state_service.get_state(self._movement_previous_state):
            current_state = self._state_service.get_current_state()
            current = current_state.key if current_state else None
            if current != self._movement_previous_state:
                self._state_service.set_state(self._movement_previous_state)
                # Mirror of `_start_movement`'s snap-back: reverting the state
                # may resize the sprite and trigger
                # `_reposition_to_keep_sprite_center`, which shifts the window
                # to preserve the sprite's screen *centre*. We want the *foot*
                # to land on the originally targeted pixel; `snap_target` is
                # the top-left computed against that foot in the pre-walk
                # (idle) frame, which is the frame we just reverted to.
                if snap_target is not None:
                    window.move_window_to(snap_target)
        self._movement_previous_state = None

        # Notify completion listeners. Iterate over a snapshot — listeners may
        # unsubscribe themselves during the callback (the common case for
        # MovementAction's one-shot wait).
        for listener in list(self._completion_listeners):
            try:
                listener()
            except Exception:  # pragma: no cover - listeners should not raise
                from ...utils.logger import get_logger as _gl
                _gl(__name__).exception("Movement completion listener raised")

    def _direction_slug(self, direction: tuple[float, float]) -> Optional[str]:
        key = direction_key(direction)
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

    def _record_move_report(self, report: str):
        self._last_move_report = report
        self._movement_reports.append(report)
        if len(self._movement_reports) > MAX_MOVE_REPORTS:
            self._movement_reports = self._movement_reports[-MAX_MOVE_REPORTS:]
        try:
            print(f"[doro move] {report}")
        except (OSError, UnicodeEncodeError):
            # OSError: stdout not available (redirected to closed file, etc.)
            # UnicodeEncodeError: Cannot encode output (rare in Python 3)
            # This is debug output, safe to ignore if it fails
            pass

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
        self._movement_start_pos = window.current_position()
        self._movement_direction_key = self._direction_slug(direction)
        self._movement_pending_report = report
        current_state = self._state_service.get_current_state()
        self._movement_previous_state = current_state.key if current_state else None
        window.reset_tick_timer(time.monotonic())
        self._set_movement_state(
            direction,
            speed_name,
            move_state=move_state,
            prefer_walking=move_state_name == self._state_service.get_default_movement_state(),
        )

        # `_set_movement_state` triggered the walking GIF, which may have a
        # different intrinsic size than the pre-walk sprite. The window
        # auto-resizes to fit (`apply_window_preferred_size`) and
        # `_reposition_to_keep_sprite_center` shifts the window top-left
        # so the sprite *centre* stays put on screen — meaning the top-left
        # we just recorded as `_movement_start_pos` is no longer where the
        # window actually is. `process_active_movement` integrates velocity
        # from the *current* top-left each tick, so an uncorrected shift
        # would compound and land Doro short of (or past) the planned
        # destination by the shift amount. Symptom: `[MOVE:to;x;y]` lands
        # at a different absolute pixel depending on which walking sprite
        # (direction) was picked.
        #
        # Undo the auto-reposition so the velocity vector and remaining
        # distance both stay valid. The visual cost is a one-frame sprite
        # jump at the start of the walk; the gain is pixel-accurate
        # landing regardless of starting direction.
        post_state_pos = window.current_position()
        if post_state_pos != self._movement_start_pos:
            window.move_window_to(self._movement_start_pos)

        # Seed the floating-point integrator at the real start, and pre-compute
        # the clamped destination so `process_active_movement` can snap to it
        # on completion instead of stopping at whatever pixel rounding lands on.
        self._movement_fpos = QtCore.QPointF(self._movement_start_pos)
        self._movement_target = window.clamp_window_position(QtCore.QPoint(
            round(self._movement_start_pos.x() + unit_x * distance),
            round(self._movement_start_pos.y() + unit_y * distance),
        ))
        current_state_obj = self._state_service.get_current_state()
        current_state = current_state_obj.key if current_state_obj else None
        self._active_movement = MovementRequest(
            direction=direction,
            distance_px=distance,
            speed_px_per_s=speed_value,
            state_key=current_state,
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
        """Select and set appropriate state for movement."""
        # Priority 1: Use explicit move_state if provided and valid
        if move_state and self._state_service.get_state(move_state.state_key):
            desired_key = move_state.state_key
        # Priority 2: Prefer default movement state if requested
        elif prefer_walking:
            desired_key = self._state_service.get_default_movement_state()
        # Priority 3: Infer state based on direction and speed
        else:
            desired_key = self._infer_state_for_movement(direction, speed_name)
            # Priority 4: Fall back to default movement state
            if not desired_key:
                desired_key = self._state_service.get_default_movement_state()

        # Only change state if we found a valid one and it's different
        current_state_obj = self._state_service.get_current_state()
        current_state_key = current_state_obj.key if current_state_obj else None
        if desired_key and desired_key != current_state_key:
            self._state_service.set_state(desired_key)

    def _infer_state_for_movement(self, direction: tuple[float, float], speed_name: str) -> Optional[str]:
        """
        Infer appropriate state for movement based on direction and speed.

        Uses data-driven approach: queries StateService for movement states
        that match the direction, instead of hardcoded string patterns.
        """
        slug = self._direction_slug(direction)
        if not slug:
            return None

        # Query movement states that support this direction
        move_states = self._state_service.find_move_states_by_direction(slug)

        # Priority 1: Exact speed match
        for move_state in move_states:
            if move_state.default_speed == speed_name:
                if self._state_service.get_state(move_state.state_key):
                    return move_state.state_key

        # Priority 2: Any state for this direction
        for move_state in move_states:
            if self._state_service.get_state(move_state.state_key):
                return move_state.state_key

        return None

    def _resolve_speed_value(self, speed_name: str) -> float:
        return self._repo.resolve_speed(speed_name)

    def _resolve_move_state_settings(self, key: str | None) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        """Resolve movement state settings via StateService only."""
        if not key:
            return None, None

        normalized = key.strip().lower()
        move_state = self._state_service.get_move_state(normalized)
        if not move_state:
            return None, None

        settings = MoveStateSettings(
            state_key=move_state.state_key,
            direction=move_state.direction,
            default_distance=move_state.default_distance,
            default_speed=move_state.default_speed,
        )
        return normalized, settings
