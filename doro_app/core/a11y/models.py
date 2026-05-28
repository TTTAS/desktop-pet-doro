"""Value types for the accessibility-tree subsystem (Phase 1d)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class A11yElement:
    """A single interactable UI element sampled from the foreground window.

    Coordinates are physical screen pixels (top-left origin) so the LLM can
    feed them straight into ``[move:to;x=;y=]``. ``role`` is normalized by
    the backend to a small vocabulary (button / link / input / menuitem /
    combobox / checkbox / tab); the serializer prints it verbatim.
    """

    role: str
    name: str
    x: int
    y: int
    width: int
    height: int
    value: Optional[str] = None
    is_password: bool = False
