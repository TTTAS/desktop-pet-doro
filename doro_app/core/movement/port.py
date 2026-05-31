"""Protocol defining window operations required by the movement system."""

from __future__ import annotations

from typing import Protocol

from PySide6 import QtCore


class MovementWindowPort(Protocol):
    """Interface for movement-related window operations."""

    def frameGeometry(self) -> QtCore.QRect: ...  # pragma: no cover

    def current_position(self) -> QtCore.QPoint: ...

    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint: ...

    def move_window_to(self, pos: QtCore.QPoint): ...

    def logical_point_for_physical(self, x: int, y: int) -> QtCore.QPoint: ...

    def sprite_foot_offset_logical(self) -> QtCore.QPoint: ...
    """Offset of the sprite's visual foot (bottom-centre) from the window's
    top-left, logical pixels. Used by `[move:to;x;y]` to back-out the
    window placement so the sprite's foot — not the invisible frame
    bottom-centre — lands on the target."""

    def get_bubble_offset(self) -> QtCore.QPointF: ...

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False): ...

    def reset_tick_timer(self, value: float): ...
