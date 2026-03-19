"""Test doubles for movement interfaces.

`MovementWindowFake` exists to let movement logic run in單元測試或 CI 等無頭環境，
不需要 Qt 視窗也能提供相同的介面行為。呼叫端可以自訂初始位置、尺寸、
限制矩形與泡泡偏移，用來驗證 `MovementManager` 的移動與面向計算是否正確，
並透過 `last_reset_time` 檢查是否有重置 tick 計時器。這樣的假件可避免測試
觸碰真實 UI，讓移動解析與執行邏輯獨立被覆蓋。
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore

from .port import MovementWindowPort


class MovementWindowFake(MovementWindowPort):
    """Headless-friendly fake implementing :class:`MovementWindowPort`.

    Use this fake in movement unit tests to simulate window geometry operations—
    clamping/moving positions, persisting bubble offsets, and tracking tick
    resets—without creating a real Qt window.
    """

    def __init__(
        self,
        *,
        origin: Optional[QtCore.QPoint] = None,
        size: Optional[QtCore.QSize] = None,
        clamp_rect: Optional[QtCore.QRect] = None,
        bubble_offset: Optional[QtCore.QPointF] = None,
    ):
        self._rect = QtCore.QRect(origin or QtCore.QPoint(0, 0), size or QtCore.QSize(100, 100))
        self._clamp_rect = clamp_rect
        self._bubble_offset = QtCore.QPointF(bubble_offset or QtCore.QPointF())
        self.last_reset_time: float | None = None

    def frameGeometry(self) -> QtCore.QRect:  # pragma: no cover - Qt binding
        return QtCore.QRect(self._rect)

    def current_position(self) -> QtCore.QPoint:
        return QtCore.QPoint(self._rect.topLeft())

    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint:
        if not self._clamp_rect:
            return QtCore.QPoint(pos)

        clamped_x = min(max(pos.x(), self._clamp_rect.left()), self._clamp_rect.right())
        clamped_y = min(max(pos.y(), self._clamp_rect.top()), self._clamp_rect.bottom())
        return QtCore.QPoint(clamped_x, clamped_y)

    def move_window_to(self, pos: QtCore.QPoint):
        self._rect.moveTopLeft(pos)

    def get_bubble_offset(self) -> QtCore.QPointF:
        return QtCore.QPointF(self._bubble_offset)

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False):  # pragma: no cover - trivial
        self._bubble_offset = QtCore.QPointF(offset)

    def reset_tick_timer(self, value: float):  # pragma: no cover - trivial
        self.last_reset_time = value

