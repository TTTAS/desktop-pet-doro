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
        foreground=lambda: 1,
        log=logs.append,
    )

    assert guard.check() == 1
    assert int(lost.winId()) in restored
    assert int(normal.winId()) not in restored
    assert logs == ["QWidget lost always-on-top; restoring it"]
    restored.clear()
    assert guard.check() == 0  # 前景沒變、旗標都在：什麼都不做
    assert restored == []


def test_reasserts_topmost_when_foreground_changes(qtbot):
    window = _window(qtbot, on_top=True)
    foreground = [1]
    restored, logs = [], []
    guard = TopmostGuard(
        is_topmost=lambda hwnd: True,  # 旗標還在，但可能被排到其他視窗後面
        make_topmost=restored.append,
        foreground=lambda: foreground[0],
        log=logs.append,
    )
    guard.check()
    restored.clear()

    guard.check()
    assert restored == []
    foreground[0] = 2  # 例如關掉相片 App，前景換成檔案總管
    guard.check()

    assert restored == [int(window.winId())]
    assert logs == []  # 例行重申不記錄，避免洗版


def test_hidden_windows_are_left_alone(qtbot):
    hidden = _window(qtbot, on_top=True)
    hidden.hide()
    restored = []
    guard = TopmostGuard(
        is_topmost=lambda hwnd: False,
        make_topmost=restored.append,
        foreground=lambda: 1,
        log=print,
    )

    guard.check()

    assert int(hidden.winId()) not in restored
