"""Port (dependency-inversion interface) for the automation subsystem.

`InputBackendPort` is what the manager calls into to read OS-level state
(foreground window class, Esc key, mouse-button state). Real
implementations live in `backend_pynput.py`; tests substitute
`FakeInputBackend`. The click-firing port lives separately as
`A11yClickerPort` (`core/a11y/clicker.py`) because production fires
clicks through UI Automation rather than a synthetic mouse event — this
keeps the user's OS cursor stationary.

`AutomationWindowPort` is the minimal subset of `QtWidgets.QWidget` the
manager needs from the Doro window. Kept narrow so headless tests can
provide a stand-in.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol


class InputBackendPort(Protocol):
    """OS-level input observer + window-class sampler.

    Production wires this to pynput (Esc key + left-button state) +
    platform window-class helpers. The synthetic-click responsibility
    has moved to `A11yClickerPort` (UIA InvokePattern, cursor-free).
    """

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        """Return the window-class string at the given screen point, or None.

        Must NOT read window title, content, pixels, or any other private data.
        Only the class (X11 `WM_CLASS` / Win32 `GetClassName`).
        """

    def read_handle_at(self, x: int, y: int) -> Optional[int]:
        """Return the OS top-level window handle at the given point, or None.

        Used in tandem with :meth:`read_foreground_window_handle` so the
        manager can refuse clicks on background windows even when the
        z-order leaves an allowlisted class under the cursor. Returning
        ``None`` from either method skips the foreground check, which is
        the safe fallback on platforms without a real implementation.
        """

    def read_foreground_window_handle(self) -> Optional[int]:
        """Return the OS top-level handle of the focused window, or None."""

    def read_pid_of_handle(self, handle: int) -> Optional[int]:
        """Return the PID owning ``handle``, or None when unavailable.

        Lets the manager treat any Doro-owned top-level window (sprite,
        chat dialog, warning overlay, settings frame…) as aligned with
        the click target — refusing only when a *different* process holds
        the foreground.
        """

    def read_class_of_handle(self, handle: int) -> Optional[str]:
        """Return the window class for ``handle``, or None.

        Diagnostic-only: identifies which window blocked a
        rejected-not-foreground click. Same privacy contract as
        :meth:`read_window_class_at` — class only, never title or content.
        """

    def is_left_button_pressed(self) -> bool:
        """Return True if the OS reports the left mouse button currently held."""

    def install_esc_listener(self, on_esc: Callable[[], None]) -> None:
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
        flow through to the UIA invoke path as an off-screen coord.
        """

    def screen_geometry_physical(self) -> tuple[int, int, int, int]:
        """Return (left, top, width, height) of Doro's current screen.

        Preferred over :meth:`screen_size_physical` for clamping because
        secondary monitors don't sit at origin (0, 0). A target on a
        legitimately positioned side monitor would otherwise be clamped
        into the primary monitor's range.
        """

    def device_pixel_ratio(self) -> float:
        """Return the DPR of Doro's current screen (1.0 when unknown).

        Lets the manager scale logical-pixel thresholds (e.g. the click
        proximity guard) before comparing against physical-pixel
        distances, so high-DPI screens don't halve the allowed range.
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
