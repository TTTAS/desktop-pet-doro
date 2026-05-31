"""Tests for `[move:to;x=X;y=Y]` — the absolute-coordinate movement form
added in Phase 1c so the LLM can position Doro before issuing `[mouse:click]`.

We exercise `MovementManager.handle_move_bracket` directly with a real
`MovementWindowFake` and a stub StateService. No Qt event loop required.
"""

from __future__ import annotations

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
        reports: list[str] = []

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


