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

    def screen_size_physical(self) -> tuple[int, int]:
        """Return (width, height) of the screen in physical px.

        Used by the manager to safety-clamp the click coordinate when it
        comes from `click_target_provider` (which lives in physical space
        like the a11y tree). A stale or miscomputed target should not
        flow through to `click_left` as an off-screen coord.
        """


class WindUpAnimatorPort(Protocol):
    """Drives the visual wind-up animation during a click.

    Real implementation (Qt side) switches the current display state to
    the protected ``click_action`` state registered by
    :class:`ActionService`; tests provide a recording stub. Both calls
    are optional from the manager's perspective — they MUST be safe to
    invoke even when no GIF is bound (the implementation handles the
    fallback chain).
    """

    def begin(self) -> None:
        """Start playing the click wind-up animation."""

    def end(self) -> None:
        """Restore the prior display state. Called at every wind-up
        exit path (fired, aborted, allowlist miss, grace-exceeded).
        """


class ClickWarningOverlayPort(Protocol):
    """Draws a red warning frame around the click target during wind-up.

    Gives the user a clear visual confirmation of which a11y element the
    pending click will land on, so the 1.5s Esc-cancel window is actually
    usable. The overlay is purely informational — it does NOT influence
    where the click fires (that still tracks Doro's foot position).

    Both methods MUST be safe to call unconditionally: ``begin(None)``
    when there's no element bounds to show (e.g. raw x/y move) should be
    a no-op, and ``end()`` must be idempotent because it's invoked from
    every wind-up exit path.
    """

    def begin(self, bounds_physical: Optional[tuple[int, int, int, int]]) -> None:
        """Show the warning frame at the given physical-pixel bounds.

        ``None`` means no a11y element was resolved for this click; the
        implementation should not display anything.
        """

    def end(self) -> None:
        """Hide the warning frame. Called at every wind-up exit path."""
