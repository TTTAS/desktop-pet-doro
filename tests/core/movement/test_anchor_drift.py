"""Regression tests for the anchor-drift fix in `_start_movement`.

When `_set_movement_state` switches to a walking GIF, the underlying
sprite may have a different intrinsic size than the pre-walk sprite.
`apply_window_preferred_size` → `_reposition_to_keep_sprite_center` then
shifts the window top-left so the sprite *centre* stays put on screen.
Without correction, `process_active_movement` (which integrates velocity
from the post-shift top-left) would accumulate that shift and miss the
intended destination — symptom: `[MOVE:to;x;y]` lands at a different
absolute pixel depending on which walking sprite (direction) was picked.

The fix in `_start_movement` undoes the post-state-change shift by
snapping the window back to the pre-state-change position.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6 import QtCore

from doro_app.core.movement.fakes import MovementWindowFake
from doro_app.core.movement.manager import MovementManager
from doro_app.core.movement.repository import MovementRepository


def _make_manager_with_state_shift(*, shift_dx: int, shift_dy: int):
    """Build a MovementManager whose state_service side-effects shift the
    window when `set_state` is called — mimicking what
    `_reposition_to_keep_sprite_center` does in production when a
    state change resizes the window."""
    window = MovementWindowFake(
        origin=QtCore.QPoint(100, 100),
        size=QtCore.QSize(100, 100),
        clamp_rect=QtCore.QRect(0, 0, 1920, 1080),
    )
    state_service = MagicMock()
    state_service.get_default_movement_state.return_value = "walking"
    state_service.get_move_state.return_value = None
    state_service.get_state.return_value = MagicMock()
    state_service.get_current_state.return_value = MagicMock(key="idle")
    state_service.find_move_states_by_direction.return_value = []

    def _shift_on_state_change(key, force=False):
        current = window.current_position()
        window.move_window_to(QtCore.QPoint(current.x() + shift_dx, current.y() + shift_dy))
        return True

    state_service.set_state = MagicMock(side_effect=_shift_on_state_change)

    repo = MovementRepository(Path("/nonexistent/movements.json"))
    manager = MovementManager(window=window, state_service=state_service, movement_repo=repo)
    return manager, window, state_service


class TestAnchorDriftFix:
    def test_state_change_shift_is_undone(self):
        """After `_set_movement_state` causes a position shift, the manager
        snaps the window back so the movement loop starts from where the
        target-position calculation assumed."""
        manager, window, _ = _make_manager_with_state_shift(shift_dx=5, shift_dy=-3)
        pre_pos = window.current_position()

        manager.handle_move_bracket("move:to;x=400;y=300", [])

        # The state-change side-effect would have shifted by (5, -3) but the
        # snap-back undoes it. The next call to `process_active_movement`
        # will integrate velocity from `pre_pos`, matching the velocity
        # vector that was planned from there.
        assert window.current_position() == pre_pos

    def test_endpoint_independent_of_state_shift_direction(self):
        """The whole point of the fix: regardless of which way the state
        change shifts the window, Doro lands at (approximately) the same
        endpoint when driven by `process_active_movement`."""
        # Walk to the same target from the same start, varying only the
        # state-change shift direction (mimics picking a different
        # walking sprite size per direction).
        endpoints: list[QtCore.QPoint] = []
        for shift_dx, shift_dy in [(0, 0), (5, -3), (-7, 4)]:
            manager, window, _ = _make_manager_with_state_shift(
                shift_dx=shift_dx, shift_dy=shift_dy,
            )
            manager.handle_move_bracket("move:to;x=400;y=300", [])
            # Drive the dt-loop to completion.
            for _ in range(200):
                manager.process_active_movement(0.05)
                if not manager.has_active_movement:
                    break
            endpoints.append(window.current_position())

        # All three endpoints should match within a few pixels (the
        # completion threshold drives sub-pixel rounding).
        for ep in endpoints[1:]:
            assert abs(ep.x() - endpoints[0].x()) <= 2
            assert abs(ep.y() - endpoints[0].y()) <= 2
