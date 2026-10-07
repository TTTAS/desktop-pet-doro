from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore

from doro_app.core.action import Action, ActionDispatcher, VisualPhase
from doro_app.core.idle_behavior_manager import (
    ACTIVITY_PROFILES,
    IdleActionType,
    IdleBehaviorManager,
)


@pytest.fixture
def pet_idle(qapp, tmp_path):
    lines = tmp_path / "lines.txt"
    lines.write_text("陪你。\n走走！\n陪你。\n", encoding="utf-8")
    current = ["idle"]
    states = Mock()
    states.get_current_state.side_effect = lambda: SimpleNamespace(key=current[0])
    states.get_current_state_key.side_effect = lambda: current[0]
    states.set_state.side_effect = lambda key, **_: current.__setitem__(0, key) or True
    states.visible_state_keys.return_value = ["idle", "happy", "walking"]
    states.is_movement_only_state.side_effect = lambda key: key == "walking"
    states.is_transitioning.return_value = False
    callbacks = []
    schedule = lambda ms, callback: callbacks.append(callback)
    dispatcher = ActionDispatcher(states, schedule)
    movement = Mock(has_active_movement=False, active_movement=None)
    listeners = []
    movement.add_completion_listener.side_effect = lambda callback: (
        listeners.append(callback) or (lambda: listeners.remove(callback))
    )

    def walk(*_):
        movement.active_movement = object()
        movement.has_active_movement = True

    def stop():
        movement.active_movement = None
        movement.has_active_movement = False
        states.set_state("idle")
        for callback in listeners.copy():
            callback()

    movement.apply_directional_walk.side_effect = walk
    movement.cancel_active_movement.side_effect = stop
    chat = Mock(is_inflight=False, is_web_busy=False)
    options = {
        "quiet": False,
        "effects": True,
        "busy": False,
        "age": 100,
        "profile": "lively",
        "now": 0,
    }
    effect = Mock()
    idle = IdleBehaviorManager(
        companion_file=lines,
        chat_orchestrator=chat,
        movement_manager=movement,
        state_service=states,
        idle_seconds_provider=lambda: options["age"],
        mark_activity=Mock(),
        action_dispatcher=dispatcher,
        schedule=schedule,
        interaction_busy=lambda: options["busy"],
        quiet_provider=lambda: options["quiet"],
        effects_enabled=lambda: options["effects"],
        profile_provider=lambda: options["profile"],
        micro_effect=effect,
        clock=lambda: options["now"],
    )
    yield SimpleNamespace(
        idle=idle,
        states=states,
        movement=movement,
        chat=chat,
        dispatcher=dispatcher,
        callbacks=callbacks,
        options=options,
        effect=effect,
        schedule=schedule,
        current=current,
    )
    idle._timer.stop()


@pytest.mark.parametrize("profile", list(ACTIVITY_PROFILES))
def test_profile_controls_timer_and_stride(pet_idle, profile):
    p = pet_idle
    p.options["profile"] = profile
    p.idle.reset()
    low, high, short, long = ACTIVITY_PROFILES[profile]
    assert low * 1000 <= p.idle._timer.interval() <= high * 1000
    _, distance = p.idle._walk()
    assert short <= distance <= long


def test_quiet_only_plays_local_effect_and_respects_switch(pet_idle):
    p = pet_idle
    p.options["quiet"] = True
    p.idle._on_timer()
    p.effect.assert_called_once_with("stretch")
    p.movement.apply_directional_walk.assert_not_called()
    p.chat.speak_line.assert_not_called()
    p.states.set_state.assert_not_called()
    assert 45000 <= p.idle._timer.interval() <= 90000
    p.effect.reset_mock()
    p.options["effects"] = False
    p.idle._on_timer()
    p.effect.assert_not_called()


@pytest.mark.parametrize("gate", ["busy", "age", "chat", "web", "movement", "transition"])
@pytest.mark.parametrize("quiet", [False, True])
def test_busy_or_recent_interaction_defers_every_expression(pet_idle, gate, quiet):
    p = pet_idle
    p.options["quiet"] = quiet
    if gate == "busy":
        p.options["busy"] = True
    elif gate == "age":
        p.options["age"] = 2
    elif gate == "chat":
        p.chat.is_inflight = True
    elif gate == "web":
        p.chat.is_web_busy = True
    elif gate == "movement":
        p.movement.has_active_movement = True
    else:
        p.states.is_transitioning.return_value = True
    p.idle._on_timer()
    p.effect.assert_not_called()
    p.idle._mark_activity.assert_not_called()
    p.movement.apply_directional_walk.assert_not_called()
    if not quiet:
        assert 2000 <= p.idle._timer.interval() <= 3000


def test_speech_cooldown_and_no_consecutive_line_or_action(pet_idle, monkeypatch):
    p = pet_idle
    p.idle._do_speak()
    first = p.chat.speak_line.call_args.args[0]
    p.idle._do_speak()
    assert p.chat.speak_line.call_args.args[0] != first
    captured = []

    def choose(items):
        captured.append(items)
        return items[0]

    monkeypatch.setattr("doro_app.core.idle_behavior_manager.random.choice", choose)
    p.idle._last_action = IdleActionType.MOVE
    p.idle._do_transition = Mock()
    p.options["now"] = 89
    p.idle._on_timer()
    assert IdleActionType.MOVE not in captured[0]
    assert IdleActionType.SPEAK not in captured[0]
    assert IdleActionType.WALK_AND_SPEAK not in captured[0]
    captured.clear()
    p.options["now"] = 90
    p.idle._do_move = Mock()
    p.idle._on_timer()
    assert IdleActionType.SPEAK in captured[0]


def test_walk_points_inward_at_corner(pet_idle):
    p = pet_idle
    window = Mock()
    window.current_position.return_value = QtCore.QPoint(0, 0)
    window.clamp_window_position.side_effect = lambda point: QtCore.QPoint(
        min(800, max(0, point.x())), min(600, max(0, point.y()))
    )
    p.idle._window = window
    for _ in range(20):
        (dx, dy), distance = p.idle._walk()
        assert dx >= 0 and dy >= 0 and distance >= 24


def test_pose_restores_then_stale_timer_cannot_override_user_pose(pet_idle):
    p = pet_idle
    p.idle._do_transition()
    assert p.current[0] == "happy"
    p.callbacks.pop(0)()
    assert p.current[0] == "idle"
    p.idle._do_transition()
    p.idle.interrupt()
    p.states.set_state("user_pose")
    for callback in p.callbacks:
        callback()
    assert p.current[0] == "user_pose"


def test_interrupt_walk_preserves_queued_user_action_and_its_pose(pet_idle):
    p = pet_idle
    p.idle._do_walk_and_speak()
    user = Action("user", [VisualPhase(p.states, "user_pose", 5000, p.schedule)])
    p.dispatcher.dispatch(user)
    p.idle.interrupt()
    assert p.dispatcher.current is user
    assert p.current[0] == "user_pose"
    p.movement.cancel_active_movement.assert_called_once()
    p.chat.speak_line.assert_not_called()
    p.idle.interrupt()
    assert p.dispatcher.current is user


def test_interruption_does_not_cancel_replacement_walk(pet_idle):
    p = pet_idle
    p.idle._do_move()
    replacement = object()
    p.movement.active_movement = replacement
    p.idle.interrupt()
    assert p.movement.active_movement is replacement
    p.movement.cancel_active_movement.assert_not_called()


@pytest.mark.parametrize("allowed", [["happy"], ["play"], [], ["deleted", "walking"]])
def test_autonomous_poses_use_only_allowed_visible_nonmovement_states(pet_idle, allowed):
    p = pet_idle
    p.states.visible_state_keys.return_value = [
        "idle",
        "happy",
        "angry",
        "failure",
        "play",
        "walking",
    ]
    p.idle._pose_keys = lambda: allowed
    p.idle._do_transition()
    if allowed in (["happy"], ["play"]):
        assert p.current[0] == allowed[0]
    else:
        assert p.current[0] == "idle"
        assert p.dispatcher.is_idle
        p.effect.assert_called_once()


def test_leaving_quiet_replaces_long_timer_and_walks_only_after_grace(pet_idle):
    p = pet_idle
    p.options["quiet"] = True
    p.idle.reset()
    assert p.idle._timer.interval() >= 45000
    p.options["quiet"] = False
    p.idle.on_mode_changed(False)
    assert p.idle._timer.interval() == 4000
    p.options["age"] = 2
    p.idle._on_timer()
    p.movement.apply_directional_walk.assert_not_called()
    p.options["age"] = 4
    p.idle._on_timer()
    p.movement.apply_directional_walk.assert_called_once()
    p.chat.speak_line.assert_not_called()
    assert 6000 <= p.idle._timer.interval() <= 12000


def test_entering_quiet_cancels_resume_and_owned_walk(pet_idle):
    p = pet_idle
    p.idle.on_mode_changed(False)
    p.idle._on_timer()
    assert p.movement.has_active_movement
    p.options["quiet"] = True
    p.idle.on_mode_changed(True)
    p.movement.cancel_active_movement.assert_called_once()
    assert not p.movement.has_active_movement
    assert 45000 <= p.idle._timer.interval() <= 90000
    p.idle._on_timer()
    p.movement.apply_directional_walk.assert_called_once()
    p.effect.assert_called_once_with("stretch")


def test_busy_resume_retries_promptly_without_losing_first_walk(pet_idle):
    p = pet_idle
    p.idle.on_mode_changed(False)
    p.options["busy"] = True
    p.idle._on_timer()
    p.movement.apply_directional_walk.assert_not_called()
    assert 2000 <= p.idle._timer.interval() <= 3000
    p.options["busy"] = False
    p.idle._on_timer()
    p.movement.apply_directional_walk.assert_called_once()


def test_no_pose_or_effect_does_not_waste_attempts_or_starve_walking(pet_idle, monkeypatch):
    p = pet_idle
    p.options["effects"] = False
    p.idle._pose_keys = lambda: ["deleted", "walking"]
    p.idle._last_speech = p.options["now"]
    p.idle._last_action = IdleActionType.MOVE
    choices = []
    monkeypatch.setattr(
        "doro_app.core.idle_behavior_manager.random.choice",
        lambda items: choices.extend(items) or items[0],
    )
    p.idle._on_timer()
    assert set(choices) == {IdleActionType.MOVE}
    p.movement.apply_directional_walk.assert_called_once()


def test_lively_profile_is_faster_but_other_preferences_are_preserved(pet_idle):
    p = pet_idle
    assert ACTIVITY_PROFILES["lively"] == (6, 12, 100, 240)
    for profile, low, high in [("balanced", 40, 75), ("calm", 90, 150)]:
        p.options["profile"] = profile
        p.idle.on_mode_changed(False)
        p.idle._on_timer()
        assert low * 1000 <= p.idle._timer.interval() <= high * 1000
        p.idle.interrupt()
