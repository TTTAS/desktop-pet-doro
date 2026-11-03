"""Value types for the accessibility-tree subsystem (Phase 1d)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class A11yElement:
    """A single interactable UI element sampled from the foreground window.

    Coordinates are physical screen pixels (top-left origin). The model sees
    them only as a ``box`` hint; a click names the element's id and
    ``A11yService.element_center`` turns it back into a point. ``role`` is normalized by
    the backend to a small vocabulary (button / link / input / menuitem /
    combobox / checkbox / tab); the serializer prints it verbatim.
    """

    role: str
    name: str
    x: int
    y: int
    width: int
    height: int
    value: str | None = None
    is_password: bool = False
