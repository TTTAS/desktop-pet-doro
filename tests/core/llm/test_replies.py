"""Character reply schema: forgiving about details, strict about speaking."""

from __future__ import annotations

from doro_app.core.llm import character_reply_model, parse_reply


def test_unknown_state_and_bad_move_are_dropped_but_line_survives():
    model = character_reply_model(["idle", "stand"])

    reply, problem = parse_reply(
        '{"state":"sleepy","line":"嗨","move":{"dir":"north","distance":5}}', model
    )

    assert problem == ""
    assert (reply.state, reply.line, reply.move) == (None, "嗨", None)


def test_valid_move_is_kept_with_its_vector():
    model = character_reply_model(["idle"])

    reply, _ = parse_reply(
        '{"state":"idle","line":"走囉","move":{"dir":"left","distance":80}}', model
    )

    assert reply.state == "idle"
    assert reply.move.vector == (-1, 0)
    assert reply.move.distance == 80


def test_move_beyond_600px_is_dropped():
    model = character_reply_model(["idle"])

    reply, _ = parse_reply('{"line":"走囉","move":{"dir":"left","distance":900}}', model)

    assert reply.move is None


def test_simplified_line_is_converted_to_taiwan_traditional():
    model = character_reply_model(["idle"])

    reply, _ = parse_reply('{"line":"新旗舰居然都要万元档了！点击看看"}', model)

    assert reply.line == "新旗艦居然都要萬元檔了！點選看看"


def test_empty_line_is_a_broken_reply():
    model = character_reply_model(["idle"])

    reply, problem = parse_reply('{"state":"idle","line":"  "}', model)

    assert reply is None
    assert "line" in problem


def test_worth_saying_false_allows_silence():
    model = character_reply_model(["idle"], decide_worth_saying=True)

    reply, _ = parse_reply('{"worth_saying":false,"state":null,"line":"","move":null}', model)

    assert reply.worth_saying is False
    assert reply.line == ""


def test_worth_saying_true_still_needs_a_line():
    model = character_reply_model(["idle"], decide_worth_saying=True)

    reply, _ = parse_reply('{"worth_saying":true,"line":""}', model)

    assert reply is None


def test_schema_lists_every_field_as_required_and_limits_states():
    model = character_reply_model(["idle", "stand"], decide_worth_saying=True)
    schema = model.model_json_schema(mode="serialization")

    assert schema["required"] == ["worth_saying", "state", "line", "move"]
    assert list(schema["properties"]) == ["worth_saying", "state", "line", "move"]
    state_enum = schema["properties"]["state"]["anyOf"][0]["enum"]
    assert state_enum == ["idle", "stand"]


def test_no_known_states_accepts_any_state_text():
    model = character_reply_model([])

    reply, _ = parse_reply('{"state":"whatever","line":"嗨"}', model)

    assert reply.state == "whatever"
