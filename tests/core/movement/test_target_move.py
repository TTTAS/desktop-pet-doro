"""Tests for `[move:to;x=X;y=Y]` — the absolute-coordinate movement form
added in Phase 1c so the LLM can position Doro before issuing `[mouse:click]`.

We exercise `MovementManager.handle_move_bracket` directly with a real
`MovementWindowFake` and a stub StateService. No Qt event loop required.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock

from PySide6 import QtCore

from doro_app.core.movement.fakes import MovementWindowFake
from doro_app.core.movement.manager import MovementManager
from doro_app.core.movement.repository import MovementRepository


def _make_manager(*, origin=(0, 0), clamp=(0, 0, 1920, 1080)):
    window = MovementWindowFake(
        origin=QtCore.QPoint(*origin),
        size=QtCore.QSize(100, 100),
        clamp_rect=QtCore.QRect(*clamp),
    )

    state_service = MagicMock()
    state_service.get_default_movement_state.return_value = "walking"
    state_service.get_move_state.return_value = None
    state_service.get_state.return_value = MagicMock()  # truthy
    state_service.get_current_state.return_value = MagicMock(key="idle")
    state_service.find_move_states_by_direction.return_value = []
    state_service.set_state = MagicMock()

    repo = MovementRepository(Path("/nonexistent/movements.json"))
    # Repository has sensible defaults even without the file.
    manager = MovementManager(
        window=window,
        state_service=state_service,
        movement_repo=repo,
    )
    return manager, window


class TestParseTo:
    def test_basic_to_starts_movement(self):
        manager, window = _make_manager(origin=(0, 0))
        reports: list[str] = []

        consumed = manager.handle_move_bracket("move:to;x=400;y=300", reports)

        assert consumed is True
        # No error reports — movement was queued.
        assert all(not r.startswith("[移動錯誤]") for r in reports)
        assert manager.has_active_movement is True

    def test_to_alias_goto_also_works(self):
        manager, window = _make_manager(origin=(0, 0))
        reports: list[str] = []

        consumed = manager.handle_move_bracket("move:goto;x=200;y=200", reports)

        assert consumed is True
        assert manager.has_active_movement is True


class TestValidation:
    def test_missing_x_returns_error(self):
        manager, _ = _make_manager()
        reports: list[str] = []
        manager.handle_move_bracket("move:to;y=100", reports)
        assert manager.has_active_movement is False
        assert any("需要 x 與 y 參數" in r for r in reports)

    def test_missing_y_returns_error(self):
        manager, _ = _make_manager()
        reports: list[str] = []
        manager.handle_move_bracket("move:to;x=100", reports)
        assert manager.has_active_movement is False
        assert any("需要 x 與 y 參數" in r for r in reports)

    def test_negative_coords_rejected(self):
        manager, _ = _make_manager()
        reports: list[str] = []
        manager.handle_move_bracket("move:to;x=-100;y=100", reports)
        assert manager.has_active_movement is False
        assert any("不可為負" in r for r in reports)

    def test_non_numeric_coords_rejected(self):
        manager, _ = _make_manager()
        reports: list[str] = []
        manager.handle_move_bracket("move:to;x=foo;y=bar", reports)
        assert manager.has_active_movement is False
        assert any("必須為數字" in r for r in reports)


class TestClamping:
    def test_excessive_x_clamps_to_screen_bounds(self):
        # clamp_rect is (0, 0, 1920, 1080) — origin/right/bottom
        manager, window = _make_manager(origin=(0, 0), clamp=(0, 0, 1920, 1080))
        reports: list[str] = []
        manager.handle_move_bracket("move:to;x=99999;y=99999", reports)
        # Movement starts (i.e. coordinates were clamped, not rejected).
        assert manager.has_active_movement is True

    def test_already_at_target_is_noop(self):
        # Window at (100,100), size 100x100 → foot offset (50, 99), so the foot
        # already sits at physical (150, 199). Targeting that is a no-op.
        manager, window = _make_manager(origin=(100, 100))
        reports: list[str] = []
        manager.handle_move_bracket("move:to;x=150;y=199", reports)
        # Effectively no movement queued.
        assert manager.has_active_movement is False
        # No error either — it's a valid no-op.
        assert all(not r.startswith("[移動錯誤]") for r in reports)


class TestFootPlacement:
    def test_top_left_backs_out_foot_offset(self):
        # Foot target physical (200,200); window 100x100 → foot offset (50,99),
        # so the window top-left must end up at (150, 101) to put the foot there.
        manager, window = _make_manager(origin=(1000, 1000))

        report = manager.apply_target_move(200, 200)

        assert manager.has_active_movement is True
        assert report is not None
        assert "位置 150, 101" in report


class TestSpriteFootOffset:
    """`_handle_target_move` should back-out the window top-left from the
    *sprite* foot offset, not the legacy frame-bottom-centre. Anchoring on
    the sprite is what makes the visible Doro line up with the target."""

    def test_uses_sprite_foot_offset_when_provided(self):
        # sprite foot sits at (30, 70) within the 100×100 window — a
        # SPRITE_OFFSET_X analogue. For foot target (200, 200), the
        # window top-left must be (200-30, 200-70) = (170, 130), NOT
        # the legacy (150, 101) from the frame bottom-centre.
        window = MovementWindowFake(
            origin=QtCore.QPoint(1000, 1000),
            size=QtCore.QSize(100, 100),
            clamp_rect=QtCore.QRect(0, 0, 1920, 1080),
            sprite_foot_offset=QtCore.QPoint(30, 70),
        )

        state_service = MagicMock()
        state_service.get_default_movement_state.return_value = "walking"
        state_service.get_move_state.return_value = None
        state_service.get_state.return_value = MagicMock()
        state_service.get_current_state.return_value = MagicMock(key="idle")
        state_service.find_move_states_by_direction.return_value = []
        state_service.set_state = MagicMock()

        repo = MovementRepository(Path("/nonexistent/movements.json"))
        manager = MovementManager(
            window=window,
            state_service=state_service,
            movement_repo=repo,
        )

        report = manager.apply_target_move(200, 200)

        assert manager.has_active_movement is True
        assert "位置 170, 130" in (report or "")


class TestMovementIntegrationPrecision:
    """Regression tests for the float-integrator + target-snap rewrite of
    `process_active_movement`. The previous integer-feedback loop dropped
    sub-pixel components on shallow diagonals (banker's rounding pinned the
    short axis to 0) and stopped at whatever pixel the threshold happened to
    land on — symptom: Doro stopped a few pixels off, and shallow diagonals
    looked jagged instead of tracing the true angle."""

    @staticmethod
    def _drive_to_completion(manager, max_ticks: int = 2000, dt: float = 0.016):
        for _ in range(max_ticks):
            if not manager.has_active_movement:
                return
            manager.process_active_movement(dt)
        raise AssertionError("movement did not complete within max_ticks")

    def test_shallow_diagonal_lands_exactly_on_target(self):
        # Foot offset is (50, 99) for a 100×100 window with the default fake.
        # Foot target (800, 130) → top-left target (750, 31). Starting at
        # (0, 0) gives a shallow diagonal (dx=750, dy=31) — the case where
        # the old integer-feedback loop pinned the y-axis to 0.
        manager, window = _make_manager(origin=(0, 0))
        manager.apply_target_move(800, 130)
        assert manager.has_active_movement is True

        self._drive_to_completion(manager)

        assert window.current_position() == QtCore.QPoint(750, 31)

    def test_shallow_diagonal_tracks_true_angle(self):
        # Drive a shallow diagonal and sample positions along the way —
        # every sample should sit within 1px of the start→target line. The
        # old loop would keep y at 0 for most of the walk, blowing past
        # this bound.
        manager, window = _make_manager(origin=(0, 0))
        manager.apply_target_move(800, 130)
        target = QtCore.QPointF(750, 31)  # matches the test above
        start = QtCore.QPointF(0, 0)
        # Line direction (normalised) and perpendicular distance helper.
        dx, dy = target.x() - start.x(), target.y() - start.y()
        line_len = math.hypot(dx, dy)
        nx, ny = -dy / line_len, dx / line_len  # unit normal

        max_perp = 0.0
        for _ in range(2000):
            if not manager.has_active_movement:
                break
            manager.process_active_movement(0.016)
            pos = window.current_position()
            perp = abs((pos.x() - start.x()) * nx + (pos.y() - start.y()) * ny)
            max_perp = max(max_perp, perp)
        assert max_perp <= 1.0, f"path drifted {max_perp:.2f}px off the straight line"

    def test_axis_aligned_move_lands_exactly(self):
        # Pure horizontal — should still hit the exact target (the old loop
        # also got this right; this guards against regression in the
        # rewrite's clamping/finalisation path).
        manager, window = _make_manager(origin=(0, 0))
        manager.apply_target_move(600, 99)  # foot y=99 → top-left y=0
        self._drive_to_completion(manager)
        assert window.current_position() == QtCore.QPoint(550, 0)

    def test_target_clamped_to_edge_finishes_cleanly(self):
        # Clamp rect ends at x=1920, so a target past it gets clamped to
        # the right edge. Movement should reach the edge and stop, not
        # spin forever trying to push past the wall.
        manager, window = _make_manager(origin=(0, 0), clamp=(0, 0, 1920, 1080))
        manager.apply_target_move(99999, 99)
        self._drive_to_completion(manager)
        end = window.current_position()
        # QRect(0,0,1920,1080).right() == 1919 — the fake clamps to that.
        assert end.x() == 1919
        assert manager.has_active_movement is False
