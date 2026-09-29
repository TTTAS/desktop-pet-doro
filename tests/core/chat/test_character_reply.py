"""Chat replies are acted out from validated fields (ADR 0005); a page answer
has no ``tool`` field, so it cannot escalate to browser or desktop (ADR 0004)."""

from unittest.mock import Mock

from doro_app.core.chat.chat_reply import ChatMove, chat_reply_model, web_answer_model
from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.llm import parse_reply


def make_orchestrator():
    state = Mock()
    state.is_movement_only_state.return_value = False
    state.get_current_state.return_value.key = "idle"
    state.visible_state_keys.return_value = ["idle", "happy"]
    orch = ChatOrchestrator(Mock(), Mock(), state)
    for name in ("_begin_operation", "_begin_login", "_begin_verify", "_begin_web_read"):
        setattr(orch, name, Mock())
    orch._queue_desktop_click = Mock()
    return orch, state


def chat(text):
    reply, problem = parse_reply(text, chat_reply_model(["idle", "happy"]))
    assert reply is not None, problem
    return reply


def test_page_answer_cannot_escalate_to_browser_or_mouse(qapp):
    orch, state = make_orchestrator()
    orch._expect_web_answer = True
    answer, _ = parse_reply(
        '{"state":"happy","line":"Found it (source)!",'
        '"move":{"dir":"right","distance":80},'
        '"tool":{"kind":"operate","goal":"buy"}}',
        web_answer_model(["idle", "happy"]),
    )

    out = orch._on_request_succeeded(answer, False)

    assert not hasattr(answer, "tool")
    assert out == "Found it (source)!"
    state.set_state.assert_called_once_with("happy")
    orch._movement.apply_directional_walk.assert_called_once_with((1, 0), 80.0)
    orch._begin_operation.assert_not_called()
    orch._queue_desktop_click.assert_not_called()


def test_chat_line_state_and_move_are_acted_out(qapp):
    orch, state = make_orchestrator()
    orch._dispatch_move_bracket = Mock(return_value=True)

    out = orch._on_request_succeeded(
        chat(
            '{"state":"happy","line":"嘿嘿走过去啰～",'
            '"move":{"dir":"up-left","distance":120,"speed":"fast"},"tool":null}'
        ),
        False,
    )

    assert out == "嘿嘿走過去囉～"
    state.set_state.assert_called_once_with("happy")
    orch._dispatch_move_bracket.assert_called_once_with(
        "MOVE:dir=up-left;distance=120;speed=fast", []
    )


def test_desktop_click_is_queued_after_moving_to_the_point(qapp):
    orch, _state = make_orchestrator()
    calls = []
    orch._dispatch_move_bracket = Mock(side_effect=lambda token, _r: calls.append(token))
    orch._queue_desktop_click = Mock(side_effect=lambda: calls.append("click"))

    orch._on_request_succeeded(
        chat('{"line":"幫人點～","move":{"x":180,"y":100},"tool":{"kind":"click"}}'), False
    )

    assert calls == ["MOVE:to;x=180;y=100", "click"]


def test_tools_start_their_features_and_hide_the_decision(qapp):
    orch, _state = make_orchestrator()
    orch._last_user_text = "原本的問題"

    assert (
        orch._on_request_succeeded(
            chat('{"line":"去看看～","tool":{"kind":"read","url":"https://a.test/x"}}'), False
        )
        == ""
    )
    orch._begin_web_read.assert_called_once_with("https://a.test/x", "原本的問題")

    orch._on_request_succeeded(chat('{"line":"幫你找找～","tool":{"kind":"verify"}}'), False)
    orch._begin_verify.assert_called_once_with("原本的問題")

    orch._on_request_succeeded(
        chat('{"line":"好～","tool":{"kind":"operate","goal":"加購物車"}}'), False
    )
    orch._begin_operation.assert_called_once_with("加購物車")

    orch._on_request_succeeded(
        chat('{"line":"開好囉","tool":{"kind":"login","url":"https://shopee.tw"}}'), False
    )
    orch._begin_login.assert_called_once_with("https://shopee.tw")


def test_second_read_in_one_turn_just_speaks(qapp):
    orch, _state = make_orchestrator()
    orch._auto_read_used = True

    out = orch._on_request_succeeded(
        chat('{"line":"這頁我看過了～","tool":{"kind":"read","url":"https://a.test"}}'), False
    )

    assert out == "這頁我看過了～"
    orch._begin_web_read.assert_not_called()


def test_malformed_move_and_tool_are_dropped_not_fatal():
    reply = chat(
        '{"line":"嗨","move":{"dir":"north","distance":5},"tool":{"kind":"read","url":"a.test"}}'
    )

    assert (reply.line, reply.move, reply.tool) == ("嗨", None, None)


def test_move_needs_exactly_one_shape():
    assert ChatMove(x=1, y=2).movement_token() == "MOVE:to;x=1;y=2"
    assert ChatMove(dir="left", distance=80).movement_token() == "MOVE:dir=left;distance=80"
    for bad in ({}, {"dir": "left"}, {"dir": "left", "distance": 5, "x": 1, "y": 2}):
        reply = chat('{"line":"嗨","move":' + str(bad).replace("'", '"') + "}")
        assert reply.move is None


def test_simulate_response_accepts_reply_json(qapp):
    orch, _state = make_orchestrator()

    assert orch.simulate_response('{"line":"測試～"}') == "測試～"
    assert orch.simulate_response("(happy) 舊格式") is None
