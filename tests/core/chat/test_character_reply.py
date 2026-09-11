from unittest.mock import Mock

from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.chat.presentation import character_instructions, parse_character_reply


def make_orchestrator():
    state = Mock()
    state.parse_state_from_action.side_effect = lambda key: key if key == "happy" else None
    state.is_movement_only_state.return_value = False
    state.get_current_state.return_value.key = "idle"
    state.visible_state_keys.return_value = ["idle", "happy"]
    orch = ChatOrchestrator(Mock(), Mock(), state)
    return orch, state


def test_page_answer_cannot_escalate_to_browser_or_mouse(qapp):
    orch, state = make_orchestrator()
    orch._expect_web_answer = True
    orch._begin_operation = Mock()
    orch._begin_login = Mock()
    orch._begin_verify = Mock()
    orch._handle_mouse_bracket = Mock()
    out = orch._on_request_succeeded(
        "(happy) Found it (source)! [MOVE:dir=right;distance=80] [mouse:click] [operate:buy] [login:https://a.test]",
        False,
    )
    assert out == "Found it (source)!"
    state.set_state.assert_called_once_with("happy")
    orch._movement.apply_directional_walk.assert_called_once_with((1, 0), 80.0)
    orch._begin_operation.assert_not_called()
    orch._begin_login.assert_not_called()
    orch._begin_verify.assert_not_called()
    orch._handle_mouse_bracket.assert_not_called()


def test_verify_answer_uses_character_presenter(qapp):
    orch, state = make_orchestrator()
    orch._current_web_request_id = "q"
    orch._on_verify_finished("q", "(happy) Result [MOVE:dir=left;distance=20]")
    state.set_state.assert_called_once_with("happy")
    orch._movement.apply_directional_walk.assert_called_once_with((-1, 0), 20.0)


def test_invalid_distance_and_coordinates_cannot_move():
    for token in (
        "[MOVE:to;x=10;y=20]",
        "[MOVE:dir=right;distance=999999]",
        "[MOVE:dir=right;distance=NaN]",
    ):
        reply = parse_character_reply("Hello " + token)
        assert reply.direction is None
        assert reply.text == "Hello"


def test_state_prompt_has_real_keys():
    assert "idle、happy" in character_instructions(["idle", "happy"])


def test_failed_page_answer_does_not_capture_next_chat(qapp):
    orch, _state = make_orchestrator()
    orch._expect_web_answer = True
    orch._get_random_network_fail_message = lambda: "offline"
    orch._on_request_failed("offline", False)
    assert not orch._expect_web_answer
