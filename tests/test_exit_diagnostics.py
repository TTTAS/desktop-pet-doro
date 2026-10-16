"""Exit diagnostics write a readable trail of close / quit / exception events."""

import atexit
import sys
import threading

import pytest
from PySide6 import QtCore, QtWidgets

from doro_app.utils.exit_diagnostics import ExitDiagnostics


@pytest.fixture
def diagnostics(qtbot, tmp_path):
    app = QtWidgets.QApplication.instance()
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    hooks = (sys.excepthook, threading.excepthook)
    diag = ExitDiagnostics(app, window, tmp_path / "exit.log")
    yield diag, window, tmp_path / "exit.log"
    app.removeEventFilter(diag)
    if diag._native_filter is not None:  # Windows only
        app.removeNativeEventFilter(diag._native_filter)
    if diag._console_handler is not None:
        import ctypes

        ctypes.windll.kernel32.SetConsoleCtrlHandler(diag._console_handler, False)
    app.aboutToQuit.disconnect(diag._about_to_quit)
    sys.excepthook, threading.excepthook = hooks
    atexit.unregister(diag._at_exit)
    import faulthandler

    faulthandler.disable()
    diag._crash_file.close()


def test_logs_start_and_main_window_close(diagnostics):
    _, window, log = diagnostics
    window.show()
    window.close()

    text = log.read_text(encoding="utf-8")
    assert "Doro started" in text
    assert "Close event -> QWidget" in text
    assert "(Doro main window), from OS=False" in text


def test_logs_quit_request_with_caller_stack(diagnostics):
    diag, _, log = diagnostics
    # 直接交給 filter;真的送 Quit 給共用的 QApplication 會讓之後的測試失去事件迴圈。
    diag.eventFilter(QtWidgets.QApplication.instance(), QtCore.QEvent(QtCore.QEvent.Type.Quit))

    text = log.read_text(encoding="utf-8")
    assert "Qt Quit event received; caller stack:" in text
    assert "test_logs_quit_request_with_caller_stack" in text


def test_logs_threads_if_process_lingers_after_event_loop(diagnostics):
    import faulthandler

    diag, _, log = diagnostics
    diag.event_loop_ended(0, linger_seconds=0.2)
    threading.Event().wait(0.6)
    faulthandler.cancel_dump_traceback_later()

    text = log.read_text(encoding="utf-8")
    assert "Qt event loop ended normally, exit code 0" in text
    assert "Thread" in text and "most recent call first" in text


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_logs_unhandled_thread_exception(diagnostics):
    _, _, log = diagnostics

    def boom():
        raise RuntimeError("worker exploded")

    thread = threading.Thread(target=boom, name="worker")
    thread.start()
    thread.join()

    text = log.read_text(encoding="utf-8")
    assert "Unhandled exception in thread" in text
    assert "RuntimeError: worker exploded" in text


def test_routine_events_stay_out_of_the_console(diagnostics, capsys):
    _, window, log = diagnostics
    dialog = QtWidgets.QDialog()
    dialog.show()
    dialog.close()
    window.show()
    window.close()

    console = capsys.readouterr().err
    text = log.read_text(encoding="utf-8")
    assert "QDialog" in text and "QDialog" not in console  # 關對話框是日常操作
    assert "(Doro main window)" in console  # 關掉 Doro 本身才顯示
