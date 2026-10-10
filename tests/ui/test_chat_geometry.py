from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from doro_app.ui.dialogs.floating_chat import FloatingChatWindow
from doro_app.ui.helpers.chat_ui_helper import ChatUIHelper
from doro_app.utils.config_manager import ConfigManager


def drag_edge(window, *, left, delta, during_move=None):
    handle = window._resize_handles[0 if left else 1]
    point = QtCore.QPoint(handle.width() // 2, handle.height() - window.BAR_HEIGHT // 2)
    assert window.childAt(handle.mapTo(window, point)) is handle
    start = handle.mapToGlobal(point)
    end = start + QtCore.QPoint(delta, 0)
    for kind, global_pos, buttons in [
        (QtCore.QEvent.Type.MouseButtonPress, start, QtCore.Qt.MouseButton.LeftButton),
        (QtCore.QEvent.Type.MouseMove, end, QtCore.Qt.MouseButton.LeftButton),
        (QtCore.QEvent.Type.MouseButtonRelease, end, QtCore.Qt.MouseButton.NoButton),
    ]:
        event = QtGui.QMouseEvent(
            kind,
            QtCore.QPointF(handle.mapFromGlobal(global_pos)),
            QtCore.QPointF(global_pos),
            (
                QtCore.Qt.MouseButton.NoButton
                if kind == QtCore.QEvent.Type.MouseMove
                else QtCore.Qt.MouseButton.LeftButton
            ),
            buttons,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(handle, event)
        if kind == QtCore.QEvent.Type.MouseMove and during_move:
            during_move()


@pytest.fixture
def window(qtbot):
    dialog = FloatingChatWindow(lambda _: True)
    qtbot.addWidget(dialog)
    dialog.show_input(QtCore.QPoint(100, 400))
    return dialog


def test_default_is_lower_center(window):
    area = window.screen().availableGeometry()
    window.restore_layout(460, None, area)
    window.show_input()
    assert window.x() == area.left() + (area.width() - 460) // 2
    assert window.y() == area.top() + round(area.height() * 0.78) - window.BAR_HEIGHT // 2
    assert area.contains(window.geometry())


@pytest.mark.parametrize("left", [False, True])
def test_edge_drag_keeps_opposite_edge_and_commits_only_on_release(window, left):
    saved = Mock()
    window.geometry_committed.connect(saved)
    origin = window.geometry()
    assert window._resize_handles[0].cursor().shape() == QtCore.Qt.CursorShape.SizeHorCursor
    assert not any(b.text() in ["＋", "-"] for b in window.findChildren(QtWidgets.QToolButton))
    drag_edge(window, left=left, delta=-37 if left else 37, during_move=saved.assert_not_called)
    assert window.width() == 497  # Continuous pixels, no 40-pixel steps.
    assert window.height() == window.BAR_HEIGHT
    assert window.y() == origin.y()
    assert (window.geometry().right() if left else window.x()) == (
        origin.right() if left else origin.x()
    )
    saved.assert_called_once_with(window.x(), window.y(), 497)
    window.expand()
    saved.reset_mock()
    bar_y = window.y() + window.height() - window.BAR_HEIGHT
    drag_edge(window, left=left, delta=37 if left else -37, during_move=saved.assert_not_called)
    assert window.width() == 460
    assert window.y() + window.height() - window.BAR_HEIGHT == bar_y
    saved.assert_called_once_with(window.x(), bar_y, 460)
    saved.reset_mock()
    window.collapse()
    window.close()
    window.show_input()
    saved.assert_not_called()
    assert window.y() == bar_y


def test_expansion_avoids_top_without_changing_saved_bar_position(window):
    saved = Mock()
    window.geometry_committed.connect(saved)
    area = window.screen().availableGeometry()
    window.show_input(QtCore.QPoint(area.left() + 30, area.top() + 20))
    before = window.pos()
    window.expand()
    assert window.y() >= area.top()
    assert window.y() + window.height() - window.BAR_HEIGHT > before.y()
    window.collapse()
    assert window.pos() == before
    saved.assert_not_called()


def test_drag_while_expanded_records_bar_position_not_history_top(window):
    saved = Mock()
    window.geometry_committed.connect(saved)
    window.expand()
    window.move(window.x() + 35, window.y() + 25)
    window.commit_geometry()
    x, y, width = saved.call_args.args
    assert (x, y) == (window.x(), window.y() + window.height() - window.BAR_HEIGHT)
    assert y != window.y()
    window.close()
    window.show_input()
    assert window.pos() == QtCore.QPoint(x, y)
    assert window.width() == width


def test_bounds_and_disconnected_screen_restore(window):
    area = window.screen().availableGeometry()
    window.restore_layout(1200, QtCore.QPoint(80000, -80000), area)
    window.show_input()
    assert area.contains(window.geometry())
    assert window.width() == min(1200, area.width())
    drag_edge(window, left=False, delta=10000)
    assert window.width() == min(1200, area.width())
    drag_edge(window, left=False, delta=-10000)
    assert window.width() == 360
    assert area.contains(window.geometry())


def test_restore_negative_monitor_coordinates(window, monkeypatch):
    area = QtCore.QRect(-1280, -200, 1280, 900)
    monkeypatch.setattr(window, "_available_area", lambda point=None: area)
    window.restore_layout(620, QtCore.QPoint(-1000, 450), area)
    assert window.pos() == QtCore.QPoint(-1000, 450)
    assert window.width() == 620
    assert area.contains(window.geometry())


def test_helper_persists_and_restores_layout_across_recreation(qtbot, tmp_path):
    path = tmp_path / "chat.ini"

    def create():
        parent = QtWidgets.QWidget()
        qtbot.addWidget(parent)
        parent.floor_geometry = lambda: parent.screen().availableGeometry()
        parent.mark_user_activity = Mock()
        core = SimpleNamespace(
            config_manager=ConfigManager(path),
            chat_orchestrator=SimpleNamespace(last_send_error=""),
            chat_response_received=Mock(),
            chat_operation_completed=Mock(),
        )
        helper = ChatUIHelper(parent, core, Mock())
        helper.show_input()
        return helper, core.config_manager

    first, config = create()
    dialog = first._chat_dialog
    dialog.show_input(QtCore.QPoint(55, 390))
    dialog.expand()
    dialog.move(85, 100)
    dialog.commit_geometry()
    drag_edge(dialog, left=False, delta=37)
    saved = list(config.ui.chat_window_position)
    assert saved[1] == dialog.y() + dialog.height() - dialog.BAR_HEIGHT
    first.shutdown()
    second, reloaded = create()
    restored = second._chat_dialog
    assert restored.pos() == QtCore.QPoint(*saved)
    assert restored.width() == 497
    assert reloaded.ui.chat_window_width == 497
    restored.close()
    second.prompt_chat()
    assert restored.pos() == QtCore.QPoint(*saved)
    assert restored.width() == 497
    second.shutdown()


@pytest.mark.parametrize("left", [False, True])
def test_drag_limit_preserves_opposite_edge(window, monkeypatch, left):
    area = QtCore.QRect(0, 0, 1800, 900)
    monkeypatch.setattr(window, "_available_area", lambda point=None: area)
    window.restore_layout(460, QtCore.QPoint(700 if left else 100, 420), area)
    window.show_input()
    fixed = window.geometry().right() if left else window.x()
    drag_edge(window, left=left, delta=-5000 if left else 5000)
    assert area.contains(window.geometry())
    assert window.width() <= 1200
    assert (window.geometry().right() if left else window.x()) == fixed
    drag_edge(window, left=left, delta=5000 if left else -5000)
    assert window.width() == 360
    assert (window.geometry().right() if left else window.x()) == fixed
