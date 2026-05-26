"""Port (dependency-inversion interface) for the automation subsystem.

`InputBackendPort` is what the manager calls into to fire synthetic events
and read OS-level state (foreground window class). Real implementations
live in `backend_pynput.py`; tests substitute `FakeInputBackend`.

`AutomationWindowPort` is the minimal subset of `QtWidgets.QWidget` the
manager needs from the Doro window. Kept narrow so headless tests can
provide a stand-in.
"""

from __future__ import annotations

from typing import Optional, Protocol


class InputBackendPort(Protocol):
    """Synthetic-input backend (pynput in production)."""

    def click_left(self, x: int, y: int) -> None:
        """Synthesize a single left-button click at OS-level physical (x, y)."""

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        """Return the window-class string at the given screen point, or None.

        Must NOT read window title, content, pixels, or any other private data.
        Only the class (X11 `WM_CLASS` / Win32 `GetClassName`).
        """

    def is_left_button_pressed(self) -> bool:
        """Return True if the OS reports the left mouse button currently held."""

    def install_esc_listener(self, on_esc: "callable") -> None:
        """Install a global Esc-only key listener. Implementations MUST ignore every
        non-Esc key in the first line of their callback and never log, store,
        or forward any other key data.
        """

    def shutdown(self) -> None:
        """Tear down listeners / background threads."""


class AutomationWindowPort(Protocol):
    """Window operations the AutomationManager depends on."""

    def foot_position_logical(self) -> tuple[int, int]:
        """Return Doro's foot position in Qt logical screen coordinates."""

    def foot_position_physical(self) -> tuple[int, int]:
        """Return Doro's foot position translated to OS physical pixels."""

    def set_mouse_transparent(self, transparent: bool) -> None:
        """Toggle Qt.WA_TransparentForMouseEvents on the Doro window.

        Used briefly around the synthetic click to avoid self-click capture.
        """

    def screen_size_logical(self) -> tuple[int, int]:
        """Return (width, height) of the available screen geometry in logical px."""
