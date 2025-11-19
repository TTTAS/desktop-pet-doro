"""Application restart and cleanup utilities."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from ..constants import RESTART_DELAY_MS

if TYPE_CHECKING:
    from ..window import DoroWindow


class AppRestarter:
    """Handles application restart and cleanup logic."""

    def __init__(self, window: DoroWindow):
        """
        Initialize AppRestarter.

        Args:
            window: The main application window
        """
        self._window = window

    def restart(self) -> None:
        """Restart doro *without* external helper script."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        # 1) Clean up resources (avoid file/lock conflicts)
        self._cleanup_resources()

        # 2) Release possible single-instance locks
        self._release_single_instance_locks()

        # 3) Build relaunch command
        relaunch_cmd = self._build_self_launch_command()
        if not relaunch_cmd:
            QtWidgets.QMessageBox.warning(
                self._window, "Restart", "Unable to determine relaunch command."
            )
            return
        if "--restarted" not in relaunch_cmd:
            relaunch_cmd.append("--restarted")

        # 4) Prefer execv under debugger to avoid IDE killing new process
        debugger_attached = bool(getattr(sys, "gettrace", lambda: None)())
        if debugger_attached:
            try:
                os.execv(relaunch_cmd[0], relaunch_cmd)
                return  # pragma: no cover - execv doesn't return
            except Exception:
                debugger_attached = False  # Fallback to old flow on failure

        # 5) Launch self as detached process
        cwd = str(Path(__file__).resolve().parent.parent.parent)
        ok, _pid = QtCore.QProcess.startDetached(
            relaunch_cmd[0], relaunch_cmd[1:], cwd
        )

        if ok:
            # 6) Quit current instance if launch succeeded
            QtCore.QTimer.singleShot(RESTART_DELAY_MS, app.quit)
        else:
            QtWidgets.QMessageBox.warning(
                self._window,
                "Restart",
                "Failed to relaunch doro. Please restart manually.",
            )

    def cleanup_on_close(self) -> None:
        """Clean up resources when window closes."""
        self._cleanup_resources()

    def _cleanup_resources(self) -> None:
        """Clean up application resources (GIF, timers, config)."""
        try:
            # Stop GIF movie
            if getattr(self._window, "_gif_movie", None):
                try:
                    self._window._gif_movie.stop()
                except Exception:
                    pass
                self._window._gif_movie = None

            # Stop main timer
            if hasattr(self._window, "_timer") and self._window._timer:
                try:
                    self._window._timer.stop()
                except Exception:
                    pass

            # Sync config
            if getattr(self._window, "_config", None):
                self._window._config.sync()
        except Exception:
            pass

    def _release_single_instance_locks(self) -> None:
        """Release possible single-instance locks safely."""
        # QLockFile pattern
        for attr in ("_lock_file", "_instance_lock", "lock_file", "instance_lock"):
            lf = getattr(self._window, attr, None)
            # QLockFile: has isLocked()/unlock()
            try:
                if (
                    lf
                    and hasattr(lf, "isLocked")
                    and lf.isLocked()
                    and hasattr(lf, "unlock")
                ):
                    lf.unlock()
            except Exception:
                pass

        # QSharedMemory pattern
        for attr in ("_shared_mem", "shared_mem", "single_instance_shm"):
            shm = getattr(self._window, attr, None)
            try:
                if (
                    shm
                    and hasattr(shm, "isAttached")
                    and shm.isAttached()
                    and hasattr(shm, "detach")
                ):
                    shm.detach()
            except Exception:
                pass

        # Clear references to avoid misuse later
        for attr in (
            "_lock_file",
            "_instance_lock",
            "lock_file",
            "instance_lock",
            "_shared_mem",
            "shared_mem",
            "single_instance_shm",
        ):
            if hasattr(self._window, attr):
                try:
                    setattr(self._window, attr, None)
                except Exception:
                    pass

    def _build_self_launch_command(self) -> list[str] | None:
        """Return argv for relaunching this app."""
        try:
            if getattr(sys, "frozen", False):  # PyInstaller etc
                exe = sys.executable or sys.argv[0]
                return [exe, *sys.argv[1:]] if exe else None

            python_exe = sys.executable or "python"

            # ★ Windows: prefer pythonw.exe over python.exe (avoids console closing new process)
            if os.name == "nt":
                try:
                    base = os.path.dirname(python_exe)
                    name = os.path.basename(python_exe).lower()
                    if name == "python.exe":
                        cand = os.path.join(base, "pythonw.exe")
                        if os.path.isfile(cand):
                            python_exe = cand
                except Exception:
                    pass

            script_path = Path(sys.argv[0]).resolve()
            if not script_path.exists():
                script_path = Path(__file__).resolve().parent.parent / "__main__.py"
            if not script_path.exists():
                return None
            return [python_exe, str(script_path), *sys.argv[1:]]
        except Exception:
            return None
