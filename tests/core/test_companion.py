from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore

from doro_app.core.companion import CompanionController
from doro_app.utils.config_manager import ConfigManager


@pytest.fixture
def companion(tmp_path):
    config = ConfigManager(tmp_path / "companion.ini")
    foot = [QtCore.QPoint(500, 750)]
    window = Mock()
    window.foot_position.side_effect = lambda: QtCore.QPoint(foot[0])
    window.floor_geometry.return_value = QtCore.QRect(0, 0, 1000, 800)
    window.sprite_foot_offset_logical.return_value = QtCore.QPoint(50, 99)
    window.clamp_window_position.side_effect = lambda p: p
    window.seconds_since_last_activity.return_value = 100
    movement = Mock()
    movement.place_foot.side_effect = lambda p: foot.__setitem__(0, p)
    states = Mock()
    states.is_movement_only_state.return_value = False
    states.get_current_state.return_value = SimpleNamespace(key="stand")
    bubble = Mock(text="")
    busy = [False]
    silence, cancel = Mock(), Mock()
    controller = CompanionController(
        window=window,
        movement=movement,
        states=states,
        config=config,
        bubble=bubble,
        busy=lambda: busy[0],
        cancel=cancel,
        silence=silence,
    )
    return SimpleNamespace(
        controller=controller,
        window=window,
        movement=movement,
        states=states,
        config=config,
        bubble=bubble,
        busy=busy,
        silence=silence,
        cancel=cancel,
        foot=foot,
    )


def test_release_near_floor_lands_once_and_rests(companion):
    c = companion
    c.controller.released()
    for _ in range(80):
        c.controller.tick(0.02)
    assert c.foot[0].y() == 799
    c.window.play_landing.assert_called_once()
    c.states.set_state.assert_called_once_with("idle")


def test_high_drag_stays_free_and_new_interaction_cancels_drop(companion):
    c = companion
    c.foot[0] = QtCore.QPoint(500, 300)
    c.controller.released()
    assert not c.controller.settling
    c.foot[0] = QtCore.QPoint(500, 750)
    c.controller.released()
    c.controller.tick(0.02)
    position = c.foot[0]
    c.controller.interrupt()
    c.controller.tick(0.02)
    assert c.foot[0] == position


def test_quiet_returns_to_saved_nest_and_persists(companion):
    c = companion
    c.controller.save_nest()
    c.foot[0] = QtCore.QPoint(300, 400)
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.silence.assert_called_once_with(True)
    c.cancel.assert_called_once()
    c.bubble.clear_text.assert_called_once()
    direction, _distance = c.movement.apply_directional_walk.call_args.args
    assert direction == (200, 399)
    restored = ConfigManager(c.config._settings.fileName())
    assert restored.ui.quiet_companion
    assert restored.ui.companion_home_x == pytest.approx(500 / 999)


def test_busy_and_click_grace_do_not_interrupt_user_work(companion):
    c = companion
    c.controller.set_quiet(True)
    c.busy[0] = True
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_not_called()
    c.busy[0] = False
    c.controller.interrupt()
    c.window.seconds_since_last_activity.return_value = 2
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_not_called()
    c.window.seconds_since_last_activity.return_value = 10
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_called_once()


def test_missing_rest_state_falls_back_without_replaying_every_tick(companion):
    c = companion
    c.config.update_ui(companion_rest_state="deleted")
    c.states.get_state.return_value = None
    c.controller.released()
    for _ in range(80):
        c.controller.tick(0.02)
    c.states.set_state.assert_called_once_with("idle")
