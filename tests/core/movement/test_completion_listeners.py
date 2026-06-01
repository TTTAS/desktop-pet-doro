"""Tests for `MovementManager.add_completion_listener` / `cancel_active_movement`.

These hooks let `MovementAction` and the `ActionDispatcher` learn when a
walk finishes without polling — they replaced the 5s defer/timeout loop
that used to live inside `AutomationManager`.
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


class TestCompletionListener:
    def test_listener_fires_on_finish(self):
        manager = _make_manager()
        fired: list[None] = []
        unsubscribe = manager.add_completion_listener(lambda: fired.append(None))

        manager.handle_move_bracket("move:to;x=400;y=300", [])
        assert manager.has_active_movement is True
        assert fired == []  # not done yet

        # Drive the movement to completion by ticking long enough to
        # cover the full distance (>500 px diagonal at ~med speed
        # finishes well within a second).
        for _ in range(120):
            manager.process_active_movement(0.05)
            if not manager.has_active_movement:
                break

        assert not manager.has_active_movement
        assert fired == [None], "listener should fire once on finish"

        # Subsequent finishes do not re-fire (only one movement was kicked off).
        manager.handle_move_bracket("move:to;x=100;y=100", [])
        for _ in range(120):
            manager.process_active_movement(0.05)
            if not manager.has_active_movement:
                break
        # Listener still subscribed — it fires again for the second movement.
        assert fired == [None, None]

        # After unsubscribe, no further fires.
        unsubscribe()
        manager.handle_move_bracket("move:to;x=50;y=50", [])
        for _ in range(120):
            manager.process_active_movement(0.05)
            if not manager.has_active_movement:
                break
        assert fired == [None, None]

    def test_cancel_active_movement_fires_listeners(self):
        manager = _make_manager()
        fired: list[None] = []
        manager.add_completion_listener(lambda: fired.append(None))

        manager.handle_move_bracket("move:to;x=400;y=300", [])
        assert manager.has_active_movement is True

        result = manager.cancel_active_movement()
        assert result is True
        assert not manager.has_active_movement
        assert fired == [None]

    def test_cancel_with_no_movement_is_noop(self):
        manager = _make_manager()
        fired: list[None] = []
        manager.add_completion_listener(lambda: fired.append(None))

        result = manager.cancel_active_movement()
        assert result is False
        assert fired == []
