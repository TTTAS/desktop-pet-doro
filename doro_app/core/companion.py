"""Quiet companionship with freely placed resting points."""

from __future__ import annotations

import math

from PySide6 import QtCore


class CompanionController:
    """Coordinates existing movement/state services without model requests.

    A resting point stores both fractions of the current monitor's work area. This
    survives resolution/taskbar changes and never returns to a removed monitor.
    """

    RETURN_DELAY = 8.0

    def __init__(self, *, window, movement, states, config, bubble, busy, cancel, silence):
        self._window = window
        self._movement = movement
        self._states = states
        self._config = config
        self._bubble = bubble
        self._busy = busy
        self._cancel = cancel
        self._silence = silence
        self._quiet = config.ui.quiet_companion
        self._return_now = self._quiet
        self._return_movement = None
        self._parked = None
        self._rest_pending = self._quiet
        self._refresh_pending = False
        self._manual_pose = False

    @property
    def quiet(self) -> bool:
        return self._quiet

    @property
    def has_rest_point(self) -> bool:
        return self._config.ui.companion_home_y is not None

    def set_quiet(self, enabled: bool) -> None:
        self._quiet = bool(enabled)
        self._config.update_ui(quiet_companion=self._quiet)
        self._config.save()
        self._silence(self._quiet)
        self.interrupt()
        if self._quiet:
            self._cancel()
            self._bubble.clear_text()
            self._return_now = True

    def save_nest(self) -> None:
        area = self._window.floor_geometry()
        foot = self._window.foot_position()
        x_ratio = (foot.x() - area.left()) / max(1, area.width() - 1)
        y_ratio = (foot.y() - area.top()) / max(1, area.height() - 1)
        self._config.update_ui(
            companion_home_x=max(0.0, min(1.0, x_ratio)),
            companion_home_y=max(0.0, min(1.0, y_ratio)),
        )
        self._config.save()
        if self._quiet:
            self._return_now = True

    def clear_rest_point(self) -> None:
        self.interrupt()
        self._config.update_ui(companion_home_y=None)
        self._config.save()
        self._parked = None

    def save_rest_state(self) -> None:
        state = self._states.get_current_state()
        if state and not self._states.is_movement_only_state(state.key):
            self._config.update_ui(companion_rest_state=state.key)
            self._config.save()

    def interrupt(self) -> None:
        owned = self._return_movement
        self._return_movement = None
        if owned is not None and self._movement.active_movement is owned:
            self._movement.cancel_active_movement()
        self._return_now = False
        self._rest_pending = self._quiet
        self._manual_pose = False

    def preserve_manual_pose(self) -> None:
        """Keep an explicitly selected pose until the next interaction."""
        self._manual_pose = True
        self._rest_pending = False
        self._refresh_pending = False

    def refresh_preferences(self) -> None:
        """Apply a newly saved resting pose in place when user work permits."""
        if not self._quiet:
            return
        self._manual_pose = False
        self._refresh_pending = True
        if not self._busy():
            self._rest()

    def _rest(self) -> None:
        self._rest_pending = False
        self._refresh_pending = False
        if self._manual_pose:
            return
        key = self._config.ui.companion_rest_state
        if not self._states.get_state(key) or self._states.is_movement_only_state(key):
            key = "idle"
        current = self._states.get_current_state()
        if current is None or current.key != key:
            self._states.set_state(key)

    def released(self) -> None:
        """Keep release within sprite bounds, without gravity or landing effects."""
        self._movement.place_foot(self._window.foot_position())

    def _home(self) -> QtCore.QPoint:
        if not self.has_rest_point:
            return self._window.foot_position()
        area = self._window.floor_geometry()
        target = QtCore.QPoint(
            area.left() + round((area.width() - 1) * self._config.ui.companion_home_x),
            area.top() + round((area.height() - 1) * self._config.ui.companion_home_y),
        )
        offset = self._window.sprite_foot_offset_logical()
        return self._window.clamp_window_position(target - offset) + offset

    def _location(self) -> tuple:
        return (
            self._window.foot_position(),
            self._window.floor_geometry(),
            self._config.ui.companion_home_x,
            self._config.ui.companion_home_y,
        )

    def _finish_return(self, *, settle_small_gap: bool = False) -> None:
        self._rest()
        # Accept a wider walking sprite's reachable arrival. Never teleport
        # across the gap left by changing back to a narrower resting sprite.
        delta = self._home() - self._window.foot_position()
        if settle_small_gap and math.hypot(delta.x(), delta.y()) <= 3:
            self._movement.place_foot(self._home())
        # A deferred state transition can still change those bounds. Accept
        # this arrival until the foot, work area or saved nest actually moves.
        self._parked = self._location()

    def tick(self, dt: float) -> None:
        busy = self._busy()
        if self._return_movement is not None:
            active = self._movement.active_movement
            if active is not self._return_movement:
                self._return_movement = None
                # Never restore a pose or position over newly started user work.
                if active is None and not busy:
                    self._finish_return()
                    return
        if busy:
            if self._quiet and not self._manual_pose:
                self._rest_pending = True
            return

        if not self._quiet:
            return
        if self._refresh_pending:
            self._rest()
            return
        if not self._return_now and (
            self._window.seconds_since_last_activity() < self.RETURN_DELAY or self._bubble.text
        ):
            return
        explicit_return = self._return_now
        self._return_now = False
        if not self.has_rest_point:
            if explicit_return or self._rest_pending:
                self._rest()
            return
        if not explicit_return and self._parked == self._location():
            if self._rest_pending:
                self._rest()
            return
        delta = self._home() - self._window.foot_position()
        distance = math.hypot(delta.x(), delta.y())
        if distance > 1.0:
            self._movement.apply_directional_walk((delta.x(), delta.y()), distance)
            self._return_movement = self._movement.active_movement
            if self._return_movement is None:
                # MovementManager also declines walks below its threshold.
                self._finish_return(settle_small_gap=True)
        elif explicit_return:
            self._finish_return()
        elif self._rest_pending:
            self._rest()
