"""TopmostGuard keeps always-on-top windows above ordinary windows."""

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


def _guard(topmost, covers, restored, logs):
    return TopmostGuard(
        is_topmost=lambda hwnd: hwnd in topmost,
        make_topmost=lambda hwnd: (restored.append(hwnd), topmost.add(hwnd)),
        covered_by=lambda hwnd: covers.get(hwnd),
        log=logs.append,
    )


def test_restores_lost_topmost_flag_only_for_on_top_windows(qtbot):
    lost = _window(qtbot, on_top=True)
    kept = _window(qtbot, on_top=True)
    normal = _window(qtbot, on_top=False)
    topmost, restored, logs = {int(kept.winId())}, [], []
    guard = _guard(topmost, {}, restored, logs)

    assert guard.check() == 1
    assert restored == [int(lost.winId())]
    assert int(normal.winId()) not in restored
    assert logs == ["QWidget lost always-on-top; restoring it"]
    restored.clear()
    assert guard.check() == 0  # 旗標都在、沒被蓋住：什麼都不做
    assert restored == []


def test_raises_again_while_another_apps_window_covers_it(qtbot):
    window = _window(qtbot, on_top=True)
    hwnd = int(window.winId())
    covers, restored, logs = {hwnd: "doro (1).gif"}, [], []
    guard = _guard({hwnd}, covers, restored, logs)

    guard.check()
    guard.check()  # 相片 App 動畫後又把視窗抬上來：繼續處理，但只記一次
    assert restored == [hwnd, hwnd]
    assert logs == ["QWidget was covered by doro (1).gif; raising it again"]

    del covers[hwnd]
    guard.check()
    assert restored == [hwnd, hwnd]


def test_hidden_windows_are_left_alone(qtbot):
    hidden = _window(qtbot, on_top=True)
    hidden.hide()
    restored = []
    guard = _guard(set(), {}, restored, [])

    guard.check()

    assert int(hidden.winId()) not in restored
