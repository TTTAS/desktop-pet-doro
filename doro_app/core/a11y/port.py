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
    """Reads interactable elements from a single focused window, and fires
    UI Automation InvokePattern actions for cursor-free clicks."""

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        """Return the window's interactable elements, or None if unavailable.

        Returning None means "no tree could be read" (backend missing,
        platform unsupported, API error) and is distinct from returning an
        empty list ("window has no interactable elements"). Implementations
        MUST read only roles, names, geometry, and (masked) field values —
        never window title or arbitrary content.
        """

    def invoke_at_physical_point(
        self,
        x: int,
        y: int,
        hwnd: Optional[int] = None,
    ) -> bool:
        """Fire the UIA InvokePattern on the element under (x, y).

        Returns True iff an element was found, exposed InvokePattern, and
        ``Invoke()`` returned without raising. Returns False for every
        other case (no backend / no element / no pattern / COM error) so
        the caller can route the click to a NOT_INVOCABLE outcome without
        falling back to a synthetic mouse event that would move the
        user's cursor.

        ``hwnd`` (optional) scopes the UIA lookup to a known top-level
        window's subtree. The Win32 hit-test in the manager already
        resolves this hwnd while skipping transparent Doro windows; by
        anchoring the UIA walk at the same root, Doro's sprite — which
        is on top in z-order but skipped by ``CWP_SKIPTRANSPARENT`` —
        cannot shadow the real target in the unscoped UIA tree. ``None``
        falls back to ``ControlFromPoint`` (current behaviour).
        """
