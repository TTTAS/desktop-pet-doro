"""Tests for `MovementManager.last_target_physical` lifecycle.

The cached `[move:to]` target feeds `AutomationManager`'s click coord
sourcing (via `take_last_target_physical` as `click_target_provider`).
It must be set when `[move:to]` succeeds, consumed exactly once per
click, and invalidated on user gestures that repudiate the cached plan
(drag-driven `cancel_active_movement`, fresh directional move).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6 import QtCore

from doro_app.core.movement.fakes import MovementWindowFake
from doro_app.core.movement.manager import MovementManager
from doro_app.core.movement.repository import MovementRepository


def _make_manager():
    window = MovementWindowFake(
        origin=QtCore.QPoint(0, 0),
        size=QtCore.QSize(100, 100),
        clamp_rect=QtCore.QRect(0, 0, 1920, 1080),
    )
    state_service = MagicMock()
    state_service.get_default_movement_state.return_value = "walking"
    state_service.get_move_state.return_value = None
    state_service.get_state.return_value = MagicMock()
    state_service.get_current_state.return_value = MagicMock(key="idle")
    state_service.find_move_states_by_direction.return_value = []
    state_service.set_state = MagicMock()
    repo = MovementRepository(Path("/nonexistent/movements.json"))
    return MovementManager(window=window, state_service=state_service, movement_repo=repo)


class TestTakeLastTargetPhysical:
    def test_returns_none_when_unset(self):
        manager = _make_manager()
        assert manager.take_last_target_physical() is None

    def test_consumes_on_read(self):
        manager = _make_manager()
        manager.last_target_physical = (190, 102)
        assert manager.take_last_target_physical() == (190, 102)
        # Subsequent reads see None — consumed.
        assert manager.take_last_target_physical() is None
        assert manager.last_target_physical is None


class TestCancelClearsTarget:
    def test_cancel_clears_target_when_active(self):
        manager = _make_manager()
        manager.handle_move_bracket("move:to;x=400;y=300", [])
        assert manager.last_target_physical == (400, 300)
        manager.cancel_active_movement()
        assert manager.last_target_physical is None

    def test_cancel_clears_target_even_when_no_active_movement(self):
        """A cached target with no in-flight movement still gets cleared.

        If the previous movement finished naturally (target stays), then
        the user drags Doro and the app fires `cancel_active_movement` as
        part of the drag handler, the target should still be invalidated
        so the next bare `[mouse:click]` uses the post-drag foot.
        """
        manager = _make_manager()
        manager.last_target_physical = (190, 102)
        # No active movement.
        result = manager.cancel_active_movement()
        assert result is False
        assert manager.last_target_physical is None


class TestDirectionalMoveClearsTarget:
    def test_directional_move_clears_cached_target(self):
        manager = _make_manager()
        manager.last_target_physical = (190, 102)
        report = manager.apply_directional_move((1, 0))
        assert report is not None  # move actually happened
        assert manager.last_target_physical is None

    def test_zero_vector_directional_move_leaves_target_untouched(self):
        """`apply_directional_move((0, 0))` is a no-op; no signal of new
        intent, so the cached target should not be cleared."""
        manager = _make_manager()
        manager.last_target_physical = (190, 102)
        report = manager.apply_directional_move((0, 0))
        assert report is None
        assert manager.last_target_physical == (190, 102)
