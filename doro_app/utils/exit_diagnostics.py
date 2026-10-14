"""Record why Doro exits, to diagnose "Doro disappeared" reports.

Everything goes to ``~/.doro/exit_diagnostics.log`` (and stderr), one line per event:

- native crashes (``faulthandler``) and unhandled Python exceptions, any thread;
- Qt close / quit requests: which window, whether the OS sent it, and the
  Python stack of whoever asked to quit;
- Windows messages that end or hide a Doro window or the session (WM_CLOSE,
  SC_CLOSE, WM_DESTROY, WM_SHOWWINDOW hide, WM_QUERYENDSESSION, WM_ENDSESSION)
  and console control events;
- the Doro main window being hidden, and the threads still alive (with their
  stacks, if the process lingers) after the Qt event loop ends;
- foreground-window changes (title + process id), to line up with the exit.

If the log shows the start line and the foreground change but **no** exit line,
the process was terminated from outside (no Python or Qt code ran).
"""

from __future__ import annotations

import atexit
import datetime
import faulthandler
import os
import sys
import threading
import traceback
from pathlib import Path

from PySide6 import QtCore, QtWidgets

DEFAULT_LOG_PATH = Path.home() / ".doro" / "exit_diagnostics.log"

_WM_DESTROY = 0x0002
_WM_CLOSE = 0x0010
_WM_SHOWWINDOW = 0x0018
_WM_QUERYENDSESSION = 0x0011
_WM_ENDSESSION = 0x0016
_WM_SYSCOMMAND = 0x0112
_SC_CLOSE = 0xF060
_CONSOLE_EVENTS = {0: "CTRL_C", 1: "CTRL_BREAK", 2: "CTRL_CLOSE", 5: "LOGOFF", 6: "SHUTDOWN"}


class ExitDiagnostics(QtCore.QObject):
    """Installed once at startup; keeps its hooks alive for the app lifetime."""

    def __init__(self, qt_app, window, log_path: Path = DEFAULT_LOG_PATH, poll_ms: int = 500):
        super().__init__(qt_app)
        self._app = qt_app
        self._window = window
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Kept open for faulthandler, which writes from a crashing thread without Python.
        self._crash_file = open(self._log_path, "a", encoding="utf-8")  # noqa: SIM115
        self._native_filter = None
        self._console_handler = None
        self._last_foreground = None

        self.log(f"=== Doro started (pid {os.getpid()}, Python {sys.version.split()[0]}) ===")
        faulthandler.enable(file=self._crash_file, all_threads=True)
        self._hook_exceptions()
        qt_app.installEventFilter(self)
        qt_app.aboutToQuit.connect(self._about_to_quit)
        qt_app.lastWindowClosed.connect(lambda: self.log("Qt lastWindowClosed emitted"))
        atexit.register(self._at_exit)
        if sys.platform == "win32":
            self._install_windows_hooks()
            self._foreground_timer = QtCore.QTimer(self)
            self._foreground_timer.timeout.connect(self._poll_foreground)
            self._foreground_timer.start(poll_ms)

    # ------------------------------------------------------------------ logging
    def log(self, message: str) -> None:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{stamp} [{threading.current_thread().name}] {message}"
        with self._lock:
            try:
                self._crash_file.write(line + "\n")
                self._crash_file.flush()
            except (OSError, ValueError):
                pass
        print(f"[exit-diag] {message}", file=sys.stderr, flush=True)

    def event_loop_ended(self, code: int, linger_seconds: float = 10.0) -> None:
        """Called after ``qt_app.exec()`` returns.

        If the process is still alive ``linger_seconds`` later, faulthandler dumps
        every thread's stack: that names the thread keeping Doro from exiting.
        """
        self.log(f"Qt event loop ended normally, exit code {code}")
        alive = [f"{t.name}{' (daemon)' if t.daemon else ''}" for t in threading.enumerate()]
        self.log(f"Threads still alive: {alive}")
        self.log(f"If Doro does not exit within {linger_seconds:g}s, all thread stacks follow:")
        faulthandler.dump_traceback_later(linger_seconds, repeat=False, file=self._crash_file)

    def _at_exit(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        self.log("Python interpreter exiting (atexit)")

    def _stack(self) -> str:
        return "".join(traceback.format_stack()[:-2]).rstrip()

    # ------------------------------------------------------------- exceptions
    def _hook_exceptions(self) -> None:
        previous_hook = sys.excepthook
        previous_thread_hook = threading.excepthook

        def excepthook(exc_type, exc, tb):
            self.log(
                "Unhandled exception:\n" + "".join(traceback.format_exception(exc_type, exc, tb))
            )
            previous_hook(exc_type, exc, tb)

        def thread_excepthook(args):
            formatted = "".join(
                traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
            )
            self.log(f"Unhandled exception in thread {args.thread}:\n{formatted}")
            previous_thread_hook(args)

        sys.excepthook = excepthook
        threading.excepthook = thread_excepthook

    # --------------------------------------------------------------- Qt events
    def eventFilter(self, obj, event):
        kind = event.type()
        if (
            kind == QtCore.QEvent.Type.Close
            and isinstance(obj, QtWidgets.QWidget)
            and obj.isWindow()
        ):
            main = " (Doro main window)" if obj is self._window else ""
            self.log(
                f"Close event -> {type(obj).__name__} {obj.windowTitle()!r}{main}, "
                f"from OS={event.spontaneous()}, visible windows={self._visible_windows()}"
            )
        elif kind == QtCore.QEvent.Type.Hide and obj is self._window:
            self.log("Doro main window hidden; caller stack:\n" + self._stack())
        elif kind == QtCore.QEvent.Type.Quit:
            self.log("Qt Quit event received; caller stack:\n" + self._stack())
        return False

    def _visible_windows(self) -> list[str]:
        return [type(w).__name__ for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()]

    def _about_to_quit(self) -> None:
        self.log("Qt aboutToQuit; caller stack:\n" + self._stack())

    # ---------------------------------------------------------- Windows only
    def _install_windows_hooks(self) -> None:
        import ctypes
        from ctypes import wintypes

        diagnostics = self

        class _Filter(QtCore.QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                try:
                    if event_type == b"windows_generic_MSG":
                        msg = wintypes.MSG.from_address(int(message))
                        diagnostics._windows_message(msg.hWnd, msg.message, msg.wParam)
                except Exception:
                    pass
                return False, 0

        self._native_filter = _Filter()
        self._app.installNativeEventFilter(self._native_filter)

        handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def console_handler(ctrl_type):
            self.log(f"Console control event: {_CONSOLE_EVENTS.get(ctrl_type, ctrl_type)}")
            return False  # let the default handling continue

        self._console_handler = handler_type(console_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_handler, True)

    def _windows_message(self, hwnd, message, wparam) -> None:
        if message == _WM_SYSCOMMAND and (int(wparam or 0) & 0xFFF0) == _SC_CLOSE:
            name = "WM_SYSCOMMAND/SC_CLOSE"
        elif message == _WM_CLOSE:
            name = "WM_CLOSE"
        elif message == _WM_QUERYENDSESSION:
            name = "WM_QUERYENDSESSION"
        elif message == _WM_ENDSESSION:
            name = "WM_ENDSESSION"
        elif message == _WM_DESTROY:
            name = "WM_DESTROY"
        elif message == _WM_SHOWWINDOW and not wparam:
            name = "WM_SHOWWINDOW(hide)"
        else:
            return
        main = " (Doro main window)" if int(hwnd or 0) == int(self._window.winId()) else ""
        self.log(f"Windows message {name} to hwnd {int(hwnd or 0):#x}{main}")

    def _poll_foreground(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        current = (int(hwnd or 0), buffer.value, pid.value)
        if current != self._last_foreground:
            self._last_foreground = current
            owner = "Doro" if pid.value == os.getpid() else f"pid {pid.value}"
            self.log(f"Foreground -> {buffer.value!r} (hwnd {current[0]:#x}, {owner})")


def install(qt_app, window, log_path: Path = DEFAULT_LOG_PATH) -> ExitDiagnostics | None:
    """Best effort: diagnostics must never stop Doro from starting."""
    try:
        diagnostics = ExitDiagnostics(qt_app, window, log_path)
    except Exception as exc:  # pragma: no cover - environment specific
        print(f"[exit-diag] could not install: {exc}", file=sys.stderr)
        return None
    print(f"[exit-diag] logging exit reasons to {log_path}", file=sys.stderr)
    return diagnostics
