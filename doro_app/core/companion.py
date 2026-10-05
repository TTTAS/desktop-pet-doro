"""Quiet companionship and short, interruptible drops onto the desktop floor."""

from __future__ import annotations

import math

from PySide6 import QtCore


class CompanionController:
    """Coordinates existing movement/state services without model requests.

    A nest is a horizontal fraction of the current monitor's work area. This
    survives resolution/taskbar changes and never returns to a removed monitor.
    """

    DROP_DISTANCE = 96
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
        self._fall_y: float | None = None
        self._fall_speed = 0.0
        self._return_now = self._quiet
        self._return_movement = None
        self._parked = None

    @property
    def quiet(self) -> bool:
        return self._quiet

    @property
    def settling(self) -> bool:
        return self._fall_y is not None

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
        ratio = (self._window.foot_position().x() - area.left()) / max(1, area.width() - 1)
        self._config.update_ui(companion_home_x=max(0.0, min(1.0, ratio)))
        self._config.save()
        if self._quiet:
            self._return_now = True

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
        self._fall_y = None
        self._return_now = False

    def _rest(self) -> None:
        key = self._config.ui.companion_rest_state
        if not self._states.get_state(key) or self._states.is_movement_only_state(key):
            key = "idle"
        current = self._states.get_current_state()
        if current is None or current.key != key:
            self._states.set_state(key)

    def released(self) -> None:
        """Only short drops attach to the floor; dragging high stays free."""
        self._movement.place_foot(self._window.foot_position())
        foot = self._window.foot_position()
        gap = self._window.floor_geometry().bottom() - foot.y()
        if 0 < gap <= self.DROP_DISTANCE:
            self._fall_y = float(foot.y())
            self._fall_speed = 0.0

    def _home(self) -> QtCore.QPoint:
        area = self._window.floor_geometry()
        target = QtCore.QPoint(
            area.left() + round((area.width() - 1) * self._config.ui.companion_home_x),
            area.bottom(),
        )
        offset = self._window.sprite_foot_offset_logical()
        return self._window.clamp_window_position(target - offset) + offset

    def _location(self) -> tuple:
        return (
            self._window.foot_position(),
            self._window.floor_geometry(),
            self._config.ui.companion_home_x,
        )

    def _finish_return(self) -> None:
        self._rest()
        # A wider walking sprite can stop short of the nest. Settle once using
        # the resting bounds instead of scheduling another impossible walk.
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
            if self.settling:
                self.interrupt()
            return
        foot = self._window.foot_position()
        floor = self._window.floor_geometry().bottom()
        if self._fall_y is not None:
            self._fall_speed += 1100.0 * max(0.0, dt)
            self._fall_y = min(float(floor), self._fall_y + self._fall_speed * dt)
            self._movement.place_foot(QtCore.QPoint(foot.x(), round(self._fall_y)))
            if self._fall_y >= floor:
                self._fall_y = None
                self._window.play_landing()
                self._rest()

        if not self._quiet or self.settling:
            return
        if not self._return_now and (
            self._window.seconds_since_last_activity() < self.RETURN_DELAY or self._bubble.text
        ):
            return
        explicit_return = self._return_now
        self._return_now = False
        if not explicit_return and self._parked == self._location():
            return
        delta = self._home() - self._window.foot_position()
        distance = math.hypot(delta.x(), delta.y())
        if distance > 1.0:
            self._movement.apply_directional_walk((delta.x(), delta.y()), distance)
            self._return_movement = self._movement.active_movement
            if self._return_movement is None:
                # MovementManager also declines walks below its threshold.
                self._finish_return()
        elif explicit_return:
            self._finish_return()
