"""Exercise real transition queues alongside movement position updates."""

import pytest
from PySide6 import QtCore

from doro_app.core.movement.fakes import MovementWindowFake
from doro_app.core.movement.manager import MovementManager
from doro_app.core.movement.repository import MovementRepository


@pytest.fixture
def moving(state_service_with_mocks, tmp_path):
    state = state_service_with_mocks
    for key in ("idle", "walking", "happy"):
        state.add_state(key, key)
    state.set_state("idle")
    window = MovementWindowFake(origin=QtCore.QPoint(100, 100))
    repo = MovementRepository(tmp_path / "movements.json")
    repo.load()
    return MovementManager(window, state, repo), window, state


def finish(manager):
    for _ in range(200):
        manager.process_active_movement(0.05)
        if not manager.has_active_movement:
            return
    pytest.fail("walk did not finish")


@pytest.mark.parametrize("cancel", [False, True])
def test_walk_ending_before_transition_does_not_leave_walking_queued(moving, cancel):
    manager, window, state = moving
    state.begin_transition()
    manager.apply_directional_walk((1, 0), 100)
    assert state.get_committed_state_key() == "idle"
    assert state.get_requested_state_key() == "walking"
    if cancel:
        manager.process_active_movement(0.05)
        manager.cancel_active_movement()
    else:
        finish(manager)
        assert window.current_position() == QtCore.QPoint(200, 100)
    assert not manager.has_active_movement
    state.end_transition()
    assert state.get_committed_state_key() == "idle"
    assert state.get_requested_state_key() == "idle"
    # A subsequent walk must not capture a stale walking state as its return state.
    manager.apply_directional_walk((0, 1), 50)
    finish(manager)
    assert state.get_committed_state_key() == "idle"


def test_newer_queued_expression_survives_walk_cleanup(moving):
    manager, _, state = moving
    state.begin_transition()
    manager.apply_directional_walk((1, 0), 100)
    state.request_state("happy")
    finish(manager)
    state.end_transition()
    assert state.get_committed_state_key() == "happy"


def test_transition_ending_during_walk_restores_idle_on_arrival(moving):
    manager, window, state = moving
    state.begin_transition()
    manager.apply_directional_walk((1, 0), 100)
    manager.process_active_movement(0.05)
    state.end_transition()
    assert state.get_committed_state_key() == "walking"
    finish(manager)
    assert window.current_position() == QtCore.QPoint(200, 100)
    assert state.get_committed_state_key() == "idle"


@pytest.mark.parametrize("ticks", [0, 2])
def test_cancel_report_uses_observed_position_not_planned_destination(moving, ticks, capsys):
    manager, window, _ = moving
    manager.apply_directional_walk((1, 0), 100)
    for _ in range(ticks):
        manager.process_active_movement(0.05)
    actual = window.current_position()
    assert actual.x() < 200
    manager.cancel_active_movement()
    output = capsys.readouterr().out
    assert "已取消" in output
    assert f"位置 {actual.x()}, {actual.y()}" in output
    assert "位置 200, 100" not in output


def test_completed_report_distinguishes_arrival(moving, capsys):
    manager, _, _ = moving
    manager.apply_directional_walk((1, 0), 100)
    finish(manager)
    output = capsys.readouterr().out
    assert "已完成" in output
    assert "位置 200, 100 (dx=100)" in output
