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

    def get_bubble_offset(self) -> QtCore.QPointF: ...

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False): ...

    def reset_tick_timer(self, value: float): ...
