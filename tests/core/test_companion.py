from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore

from doro_app.core.companion import CompanionController
from doro_app.utils.config_manager import ConfigManager


@pytest.fixture
def companion(tmp_path):
    config = ConfigManager(tmp_path / "companion.ini")
    config.update_ui(companion_home_y=1.0, companion_floor_interaction=True)
    foot = [QtCore.QPoint(500, 750)]
    window = Mock()
    window.foot_position.side_effect = lambda: QtCore.QPoint(foot[0])
    window.floor_geometry.return_value = QtCore.QRect(0, 0, 1000, 800)
    window.sprite_foot_offset_logical.return_value = QtCore.QPoint(50, 99)
    window.clamp_window_position.side_effect = lambda p: p
    window.seconds_since_last_activity.return_value = 100
    movement = Mock()
    movement.active_movement = None

    def walk(*_):
        movement.active_movement = object()

    movement.apply_directional_walk.side_effect = walk
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
    assert direction == (200, 350)
    restored = ConfigManager(c.config._settings.fileName())
    assert restored.ui.quiet_companion
    assert restored.ui.companion_home_x == pytest.approx(500 / 999)
    assert restored.ui.companion_home_y == pytest.approx(750 / 799)


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


@pytest.mark.parametrize("replacement", [None, object()])
@pytest.mark.parametrize("tick_before_click", [False, True])
def test_click_after_return_does_not_cancel_chat_work(companion, replacement, tick_before_click):
    c = companion
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.cancel.reset_mock()
    # Chat can stay busy after arrival, or replace the return with its own walk.
    c.movement.active_movement = replacement
    c.busy[0] = True
    if tick_before_click:
        c.controller.tick(0.02)
    c.controller.interrupt()
    c.cancel.assert_not_called()
    c.movement.cancel_active_movement.assert_not_called()
    c.states.set_state.assert_not_called()


def test_click_cancels_only_the_owned_return(companion):
    c = companion
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.cancel.reset_mock()
    c.controller.interrupt()
    c.cancel.assert_not_called()
    c.movement.cancel_active_movement.assert_called_once()


@pytest.mark.parametrize("trigger", ["startup", "click", "walk", "release"])
def test_grounded_without_a_drop_does_not_squat(companion, trigger):
    c = companion
    if trigger == "walk":
        c.controller.tick(0.02)
    c.foot[0] = QtCore.QPoint(500, 799)
    if trigger == "click":
        c.controller.interrupt()
    elif trigger == "release":
        c.controller.released()
    c.controller.tick(0.02)
    c.window.play_landing.assert_not_called()


def test_pose_selected_at_home_survives_until_saved(companion):
    c = companion
    c.foot[0] = QtCore.QPoint(500, 799)
    c.controller.save_nest()
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.controller.interrupt()
    c.states.get_current_state.return_value = SimpleNamespace(key="happy")
    c.states.set_state.reset_mock()
    c.window.seconds_since_last_activity.return_value = 30
    for _ in range(20):
        c.controller.tick(0.02)
    c.states.set_state.assert_not_called()
    c.controller.save_rest_state()
    assert c.config.ui.companion_rest_state == "happy"


@pytest.mark.parametrize("change", ["drag", "work_area", "nest"])
def test_parked_arrival_does_not_prevent_return_after_location_changes(companion, change):
    c = companion
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.movement.active_movement = None
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.reset_mock()
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_not_called()
    if change == "drag":
        c.controller.interrupt()
        c.foot[0] += QtCore.QPoint(-200, -100)
    elif change == "work_area":
        c.window.floor_geometry.return_value = QtCore.QRect(0, 0, 1000, 900)
    else:
        c.config.update_ui(companion_home_x=0.25)
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_called_once()


def test_walk_below_movement_threshold_settles_once(companion):
    c = companion
    c.foot[0] = QtCore.QPoint(500, 799)
    c.controller.save_nest()
    c.foot[0] += QtCore.QPoint(2, 0)
    c.movement.apply_directional_walk.side_effect = None
    c.controller.set_quiet(True)
    for _ in range(20):
        c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_called_once()
    assert c.foot[0] == QtCore.QPoint(500, 799)


@pytest.mark.parametrize("quiet", [False, True])
def test_unset_rest_point_and_disabled_floor_interaction_leave_position_free(companion, quiet):
    c = companion
    c.config.update_ui(companion_home_y=None, companion_floor_interaction=False)
    c.foot[0] = QtCore.QPoint(500, 760)
    c.controller.set_quiet(quiet)
    c.controller.released()
    for _ in range(100):
        c.controller.tick(0.02)
    assert c.foot[0] == QtCore.QPoint(500, 760)
    assert not c.controller.settling
    c.window.play_landing.assert_not_called()
    c.movement.apply_directional_walk.assert_not_called()
    # Moving again after enabling quiet must not make an implicit rest point.
    c.controller.interrupt()
    c.foot[0] = QtCore.QPoint(300, 400)
    c.controller.tick(0.02)
    c.movement.apply_directional_walk.assert_not_called()


def test_rest_point_preserves_height_across_monitor_changes(companion):
    c = companion
    c.window.floor_geometry.return_value = QtCore.QRect(-1000, -200, 1001, 801)
    c.foot[0] = QtCore.QPoint(-750, 200)
    c.controller.save_nest()
    assert c.config.ui.companion_home_x == pytest.approx(0.25)
    assert c.config.ui.companion_home_y == pytest.approx(0.5)
    c.window.floor_geometry.return_value = QtCore.QRect(0, 100, 2001, 601)
    c.foot[0] = QtCore.QPoint(900, 600)
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    assert c.movement.apply_directional_walk.call_args.args[0] == (-400, -200)
    c.movement.active_movement = None
    c.controller.tick(0.02)
    assert c.foot[0] == QtCore.QPoint(500, 400)


def test_disabling_floor_interaction_stops_fall_without_cancelling_other_work(companion):
    c = companion
    c.controller.released()
    c.controller.tick(0.02)
    foot = QtCore.QPoint(c.foot[0])
    c.controller.set_floor_interaction(False)
    for _ in range(100):
        c.controller.tick(0.02)
    assert c.foot[0] == foot
    assert not c.controller.settling
    c.cancel.assert_not_called()
    c.window.play_landing.assert_not_called()
    assert not ConfigManager(c.config._settings.fileName()).ui.companion_floor_interaction


def test_clearing_rest_point_cancels_return_and_stays_in_place(companion):
    c = companion
    c.controller.set_quiet(True)
    c.controller.tick(0.02)
    c.controller.clear_rest_point()
    c.movement.cancel_active_movement.assert_called_once()
    c.movement.active_movement = None
    c.movement.apply_directional_walk.reset_mock()
    foot = QtCore.QPoint(c.foot[0])
    c.controller.tick(0.02)
    assert c.foot[0] == foot
    c.movement.apply_directional_walk.assert_not_called()
    assert not c.controller.has_rest_point
    assert ConfigManager(c.config._settings.fileName()).ui.companion_home_y is None
