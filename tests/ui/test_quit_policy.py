"""Closing a dialog must not quit Doro; closing Doro's own main window must."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PySide6 import QtCore, QtWidgets

from doro_app.cli import install_quit_policy

_SCRIPT = textwrap.dedent(
    """
    import sys
    from PySide6 import QtCore, QtWidgets
    from doro_app.cli import install_quit_policy

    class Main(QtWidgets.QWidget):
        closed = QtCore.Signal()

    app = QtWidgets.QApplication(sys.argv)
    main = Main()
    main.setWindowFlags(QtCore.Qt.WindowType.Tool)  # like DoroWindow: off the taskbar
    if sys.argv[1] == "policy":
        install_quit_policy(app, main)
    main.show()

    def open_dialog():
        dialog = QtWidgets.QDialog(main)
        QtCore.QTimer.singleShot(50, dialog.reject)
        dialog.exec()
        QtCore.QTimer.singleShot(200, lambda: app.exit(7))

    QtCore.QTimer.singleShot(0, open_dialog)
    sys.exit(app.exec())
    """
)


def _run(mode: str) -> int:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, mode], cwd=root, env=env, timeout=60, check=False
    )
    return result.returncode


def test_closing_a_dialog_quits_a_tool_window_app_without_the_policy():
    # 重現原本的問題:主視窗是 Tool 時,關掉任何對話框 Qt 都當成「最後一個視窗關了」。
    assert _run("default") == 0


def test_closing_a_dialog_keeps_doro_running_with_the_policy():
    assert _run("policy") == 7


class _Window(QtCore.QObject):
    closed = QtCore.Signal()


def test_policy_quits_when_main_window_closes(qapp, monkeypatch):
    quits = []
    monkeypatch.setattr(QtWidgets.QApplication, "quit", lambda: quits.append(True))
    window = _Window()
    try:
        install_quit_policy(qapp, window)
        assert not qapp.quitOnLastWindowClosed()
        window.closed.emit()
        assert quits == [True]
    finally:
        qapp.setQuitOnLastWindowClosed(True)


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
