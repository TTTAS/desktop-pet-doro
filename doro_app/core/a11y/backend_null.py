"""No-op a11y backend for platforms without an implementation yet.

X11 (AT-SPI), macOS (AXUIElement), and Wayland are deferred to a later
phase. On those platforms the service uses this backend, which always
reports "no tree available" so nothing is injected into the prompt.
"""

from __future__ import annotations

from .models import A11yElement


class NullA11yBackend:
    """Always returns None — no accessibility tree is available."""

    def read_elements(self, handle: int) -> list[A11yElement] | None:
        return None

    def invoke_at_physical_point(
        self,
        x: int,
        y: int,
        hwnd: int | None = None,
    ) -> bool:
        return False
