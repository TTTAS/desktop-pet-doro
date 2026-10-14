"""TopmostGuard restores always-on-top for windows that asked for it."""

from PySide6 import QtCore, QtWidgets

from doro_app.ui.topmost_guard import TopmostGuard


def _window(qtbot, on_top: bool) -> QtWidgets.QWidget:
    widget = QtWidgets.QWidget()
    flags = QtCore.Qt.WindowType.Tool
    if on_top:
        flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
    widget.setWindowFlags(flags)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_restores_topmost_only_where_it_was_lost(qtbot):
    lost = _window(qtbot, on_top=True)
    kept = _window(qtbot, on_top=True)
    normal = _window(qtbot, on_top=False)
    topmost = {int(kept.winId())}
    restored, logs = [], []
    guard = TopmostGuard(
        is_topmost=lambda hwnd: hwnd in topmost,
        make_topmost=lambda hwnd: (restored.append(hwnd), topmost.add(hwnd)),
        log=logs.append,
    )

    assert guard.check() == 1
    assert restored == [int(lost.winId())]
    assert int(normal.winId()) not in restored
    assert "lost always-on-top" in logs[0]
    assert guard.check() == 0  # 已恢復，不重複處理


def test_hidden_windows_are_left_alone(qtbot):
    hidden = _window(qtbot, on_top=True)
    hidden.hide()
    restored = []
    guard = TopmostGuard(is_topmost=lambda hwnd: False, make_topmost=restored.append, log=print)

    guard.check()

    assert int(hidden.winId()) not in restored
