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
    state_service.find_move_states_by_direction.return_value = []

    # Track the "current state" so the revert path in `_finish_movement`
    # actually fires its `set_state(previous)` (it only fires when the
    # current key differs from the captured previous one).
    current_key = {"key": "idle"}
    state_service.get_current_state = MagicMock(
        side_effect=lambda: MagicMock(key=current_key["key"])
    )

    def _shift_on_state_change(key, force=False):
        current = window.current_position()
        window.move_window_to(QtCore.QPoint(current.x() + shift_dx, current.y() + shift_dy))
        current_key["key"] = key
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
        change shifts the window, Doro lands at exactly the same endpoint
        when driven by `process_active_movement`. With the `_finish_movement`
        snap-back in place, the final position is `_movement_target`
        regardless of revert-time shift — exact equality, not approximate."""
        endpoints: list[QtCore.QPoint] = []
        for shift_dx, shift_dy in [(0, 0), (5, -3), (-7, 4)]:
            manager, window, _ = _make_manager_with_state_shift(
                shift_dx=shift_dx, shift_dy=shift_dy,
            )
            manager.handle_move_bracket("move:to;x=400;y=300", [])
            for _ in range(200):
                manager.process_active_movement(0.05)
                if not manager.has_active_movement:
                    break
            endpoints.append(window.current_position())

        for ep in endpoints[1:]:
            assert ep == endpoints[0]

    def test_finish_snaps_back_after_state_revert(self):
        """On completion, the state-revert in `_finish_movement` triggers the
        same reposition side-effect as `_start_movement` did. Without the
        symmetric snap-back, the final foot position drifts by Δ; with it,
        the window lands exactly on `_movement_target` (the top-left planned
        in the idle/pre-walk frame, which is the frame we just reverted to)."""
        manager, window, _ = _make_manager_with_state_shift(shift_dx=11, shift_dy=-7)
        manager.handle_move_bracket("move:to;x=400;y=300", [])
        planned_target = manager._movement_target
        assert planned_target is not None
        for _ in range(200):
            manager.process_active_movement(0.05)
            if not manager.has_active_movement:
                break
        assert window.current_position() == planned_target

    def test_finish_does_not_snap_on_cancel(self):
        """Cancellation (e.g. user drags Doro mid-walk) calls
        `_finish_movement()` with no `final_position`. The snap-back must NOT
        run — Doro should stay wherever the cancel left her, not jump back
        to the original target."""
        manager, window, _ = _make_manager_with_state_shift(shift_dx=11, shift_dy=-7)
        manager.handle_move_bracket("move:to;x=400;y=300", [])
        planned_target = manager._movement_target
        assert planned_target is not None
        # Drive a couple of frames so we're partway, then cancel.
        manager.process_active_movement(0.05)
        manager.process_active_movement(0.05)
        pos_before_cancel = window.current_position()
        manager.cancel_active_movement()
        # state revert applied its (+11, -7) shift; nothing snapped it away.
        expected = QtCore.QPoint(
            pos_before_cancel.x() + 11, pos_before_cancel.y() - 7,
        )
        assert window.current_position() == expected
        assert window.current_position() != planned_target
