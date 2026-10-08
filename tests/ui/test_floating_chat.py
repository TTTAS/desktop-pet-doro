from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from doro_app.ui.dialogs.floating_chat import FloatingChatWindow


@pytest.fixture
def chat(qtbot):
    send = Mock(return_value=True)
    window = FloatingChatWindow(send)
    qtbot.addWidget(window)
    window.show_input(QtCore.QPoint(200, 400))
    yield window, send
    window.hide()


def test_persistent_input_history_and_hide_preserve_draft(chat, qtbot):
    window, send = chat
    assert not window.expanded
    assert window.testAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert window.input.isVisible()
    assert not window.history_panel.isVisible()
    qtbot.mouseClick(window.history_button, QtCore.Qt.MouseButton.LeftButton)
    assert window.expanded
    assert not window.isModal()
    window.input.setPlainText("還沒說完")
    qtbot.mouseClick(window.hide_button, QtCore.Qt.MouseButton.LeftButton)
    assert not window.isVisible()
    window.show_input(focus=True)
    assert window.isVisible() and not window.expanded
    assert window.input.toPlainText() == "還沒說完"
    window.expand()
    qtbot.keyClick(window.input, QtCore.Qt.Key.Key_Escape)
    assert not window.expanded
    assert window.input.isVisible()
    qtbot.keyClick(window.input, QtCore.Qt.Key.Key_Escape)
    assert not window.isVisible()
    send.assert_not_called()


def test_enter_sends_shift_enter_adds_line_and_ime_does_not_send(chat, qtbot):
    window, send = chat
    window.input.setPlainText("你好")
    window.input.moveCursor(QtGui.QTextCursor.MoveOperation.End)
    qtbot.keyClick(window.input, QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert window.input.toPlainText() == "你好\n"
    preedit = QtGui.QInputMethodEvent("ㄉ", [])
    QtWidgets.QApplication.sendEvent(window.input, preedit)
    qtbot.keyClick(window.input, QtCore.Qt.Key.Key_Return)
    send.assert_not_called()
    committed = QtGui.QInputMethodEvent()
    committed.setCommitString("的")
    QtWidgets.QApplication.sendEvent(window.input, committed)
    qtbot.keyClick(window.input, QtCore.Qt.Key.Key_Return)
    send.assert_called_once_with("你好\n的")
    assert not window.input.toPlainText()
    assert window.input.isVisible() and not window.expanded
    assert not window.send_button.isEnabled()


def test_synchronous_reply_follows_user_and_is_plain_text(chat):
    window, send = chat
    send.side_effect = lambda _: window.receive_reply("<b>陪你</b>\n第二行", {}) or True
    window.input.setPlainText("<img src='https://example.com/pixel'>")
    window.send()
    assert [role for role, _ in window._messages] == ["你", "Doro"]
    plain = window.transcript.toPlainText()
    assert "<img src=" in plain and "<b>陪你</b>" in plain
    assert not window.expanded  # A reply never steals focus or opens the window.
    assert window.status.text() == "我在，繼續說吧。"


def test_rejected_send_retains_draft_without_duplicate_user_entry(chat):
    window, send = chat
    send.return_value = False
    window.input.setPlainText("等一下")
    window.send()
    assert window.input.toPlainText() == "等一下"
    assert not window._messages
    assert "未送出" in window.status.text()
    assert window.history_button.text() == "!"
    send.return_value = True
    window.send()
    assert window._messages == [("你", "等一下")]


@pytest.mark.parametrize("new_draft", ["", "下一句先寫好"])
def test_async_failure_restores_sent_text_without_overwriting_new_draft(chat, new_draft):
    window, _ = chat
    window.input.setPlainText("上一句")
    window.send()
    window.input.setPlainText(new_draft)
    window.request_failed("offline", False)
    assert window.input.toPlainText() == (new_draft or "上一句")
    assert "offline" in window.status.text()
    assert "offline" in window.history_button.toolTip()


def test_status_is_separate_and_history_is_bounded_and_clearable(chat):
    window, _ = chat
    window.receive_reply("Thinking...", {"auto_hide": False})
    assert not window._messages
    assert window.status.text() == "Doro 正在想…"
    window.finish_processing()
    assert window.status.text() == "處理完成，可以繼續聊。"
    for i in range(205):
        window.receive_reply(str(i), {})
    assert len(window._messages) == 200
    assert window._messages[0] == ("Doro", "5")
    window.input.setPlainText("保留草稿")
    window.clear_history()
    assert not window._messages
    assert window.input.toPlainText() == "保留草稿"


def test_launch_and_expand_stay_inside_work_area(chat):
    window, _ = chat
    area = window.screen().availableGeometry()
    window.show_input(area.bottomRight())
    assert area.contains(window.geometry())
    window.expand()
    assert area.contains(window.geometry())


def test_handle_drags_input_without_opening_history(chat):
    window, _ = chat
    origin = window.pos()
    press = window.drag_handle.mapToGlobal(QtCore.QPoint(7, 15))
    for kind, global_pos, buttons in [
        (QtCore.QEvent.Type.MouseButtonPress, press, QtCore.Qt.MouseButton.LeftButton),
        (
            QtCore.QEvent.Type.MouseMove,
            press + QtCore.QPoint(60, 0),
            QtCore.Qt.MouseButton.LeftButton,
        ),
        (
            QtCore.QEvent.Type.MouseButtonRelease,
            press + QtCore.QPoint(60, 0),
            QtCore.Qt.MouseButton.NoButton,
        ),
    ]:
        event = QtGui.QMouseEvent(
            kind,
            QtCore.QPointF(window.drag_handle.mapFromGlobal(global_pos)),
            QtCore.QPointF(global_pos),
            (
                QtCore.Qt.MouseButton.LeftButton
                if kind != QtCore.QEvent.Type.MouseMove
                else QtCore.Qt.MouseButton.NoButton
            ),
            buttons,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(window.drag_handle, event)
    assert window.pos() == origin + QtCore.QPoint(60, 0)
    assert not window.expanded


def test_history_expands_upward_and_input_stays_in_place(chat):
    window, _ = chat
    window.layout().activate()
    input_pos = window.input.mapToGlobal(QtCore.QPoint())
    before = window.geometry()
    window.expand()
    assert window.geometry().top() < before.top()
    assert window.input.mapToGlobal(QtCore.QPoint()) == input_pos
    window.collapse()
    assert window.geometry() == before
    assert window.input.mapToGlobal(QtCore.QPoint()) == input_pos


def test_inactive_input_bar_does_not_pause_pet_and_hidden_reply_stays_hidden(chat, monkeypatch):
    window, _ = chat
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    assert not window.interacting
    window.expand()
    assert window.interacting
    window.close()
    window.receive_reply("我在這裡。", {})
    assert not window.isVisible()
    assert not window.interacting
    window.show_input()
    assert "我在這裡。" in window.transcript.toPlainText()


def test_rejection_reason_is_shown_and_success_clears_old_error(chat):
    window, send = chat
    window._rejection_reason = lambda: "Chat server URL is not configured."
    send.return_value = False
    window.input.setPlainText("你好")
    window.send()
    assert "Chat server URL is not configured." in window.status.text()
    assert "Chat server URL is not configured." in window.history_button.toolTip()
    assert not window._messages
    send.return_value = True
    window.send()
    assert window.history_button.text() != "!"
    assert "not configured" not in window.status.text()
    assert window._messages == [("你", "你好")]


def test_auto_failure_does_not_change_manual_draft_or_status(chat):
    window, _ = chat
    window.input.setPlainText("正在打字")
    previous = window.status.text()
    window.request_failed("background failed", True)
    assert window.input.toPlainText() == "正在打字"
    assert window.status.text() == previous


def test_async_error_is_plain_text_and_completion_does_not_hide_it(chat):
    window, _ = chat
    window.input.setPlainText("你好")
    window.send()
    window.receive_reply("Thinking...", {"auto_hide": False})
    reason = "HTTP 503: <b>Service unavailable</b>"
    window.request_failed(reason, False)
    window.finish_processing()
    assert reason in window.status.text()
    assert window.status.textFormat() == QtCore.Qt.TextFormat.PlainText
    assert window.history_button.text() == "!"
