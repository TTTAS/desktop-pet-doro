"""SimulateReplyDialog turns form fields into a chat reply (ADR 0005)."""

from __future__ import annotations

import json

from doro_app.core.chat.chat_reply import chat_reply_model
from doro_app.core.llm import parse_reply
from doro_app.ui.dialogs.simulate_reply_dialog import SimulateReplyDialog


def _dialog(qtbot, states=("idle", "happy")):
    dialog = SimulateReplyDialog(list(states))
    qtbot.addWidget(dialog)
    return dialog


def _select(combo, value):
    combo.setCurrentIndex(combo.findData(value))


def test_line_only_reply(qtbot):
    dialog = _dialog(qtbot)
    dialog._line_edit.setPlainText("嗨～")

    assert dialog.build_reply() == {"state": None, "line": "嗨～", "move": None, "tool": None}


def test_state_and_directional_move(qtbot):
    dialog = _dialog(qtbot)
    _select(dialog._state_combo, "happy")
    dialog._line_edit.setPlainText("走囉")
    _select(dialog._move_combo, "direction")
    _select(dialog._dir_combo, "up-left")
    dialog._distance_spin.setValue(120)
    _select(dialog._speed_combo, "fast")

    reply = dialog.build_reply()

    assert reply["state"] == "happy"
    assert reply["move"] == {"dir": "up-left", "distance": 120, "speed": "fast"}


def test_click_at_a_point(qtbot):
    dialog = _dialog(qtbot)
    dialog._line_edit.setPlainText("幫人點～")
    _select(dialog._move_combo, "point")
    dialog._x_spin.setValue(180)
    dialog._y_spin.setValue(100)
    _select(dialog._tool_combo, "click")

    reply = dialog.build_reply()

    assert reply["move"] == {"x": 180, "y": 100}
    assert reply["tool"] == {"kind": "click"}


def test_each_tool_only_sends_its_own_field(qtbot):
    dialog = _dialog(qtbot)
    dialog._url_edit.setText("https://a.test")
    dialog._query_edit.setText("找好玩的網站")
    dialog._goal_edit.setText("加購物車")

    for kind, expected in (
        ("read", {"kind": "read", "url": "https://a.test"}),
        ("login", {"kind": "login", "url": "https://a.test"}),
        ("verify", {"kind": "verify", "query": "找好玩的網站"}),
        ("operate", {"kind": "operate", "goal": "加購物車"}),
    ):
        _select(dialog._tool_combo, kind)
        assert dialog.build_reply()["tool"] == expected


def test_only_fields_for_the_chosen_move_and_tool_are_shown(qtbot):
    dialog = _dialog(qtbot)
    form = dialog._form

    assert not form.isRowVisible(dialog._dir_combo)
    assert not form.isRowVisible(dialog._url_edit)

    _select(dialog._move_combo, "point")
    _select(dialog._tool_combo, "read")

    assert form.isRowVisible(dialog._x_spin)
    assert not form.isRowVisible(dialog._dir_combo)
    assert form.isRowVisible(dialog._url_edit)
    assert not form.isRowVisible(dialog._goal_edit)


def test_invalid_form_stays_open_with_a_message(qtbot):
    dialog = _dialog(qtbot)

    dialog._on_send()
    assert "台詞" in dialog._error.text()
    assert dialog.reply_json() is None

    dialog._line_edit.setPlainText("去看看")
    _select(dialog._tool_combo, "read")
    dialog._url_edit.setText("a.test")
    dialog._on_send()

    assert "網址" in dialog._error.text()
    assert dialog.reply_json() is None


def test_accepted_json_is_a_valid_chat_reply(qtbot):
    dialog = _dialog(qtbot)
    _select(dialog._state_combo, "idle")
    dialog._line_edit.setPlainText("好，doro去看看～")
    _select(dialog._tool_combo, "read")
    dialog._url_edit.setText("https://a.test/x")

    dialog._on_send()

    text = dialog.reply_json()
    assert json.loads(text)["tool"]["url"] == "https://a.test/x"
    reply, problem = parse_reply(text, chat_reply_model(["idle", "happy"]))
    assert problem == ""
    assert reply.tool.kind == "read"
