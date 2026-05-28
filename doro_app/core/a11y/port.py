"""Port (dependency-inversion interface) for the a11y subsystem (Phase 1d).

``A11yBackendPort`` is what :class:`A11yService` calls to obtain the raw
element list for a focused window. Production implementations are
platform-specific (Windows UIA); ``NullA11yBackend`` covers platforms with
no backend yet, and ``FakeA11yBackend`` substitutes in tests.
"""

from __future__ import annotations

from typing import Optional, Protocol

from .models import A11yElement


class A11yBackendPort(Protocol):
    """Reads interactable elements from a single focused window."""

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        """Return the window's interactable elements, or None if unavailable.

        Returning None means "no tree could be read" (backend missing,
        platform unsupported, API error) and is distinct from returning an
        empty list ("window has no interactable elements"). Implementations
        MUST read only roles, names, geometry, and (masked) field values —
        never window title or arbitrary content.
        """
