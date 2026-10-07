"""Bounded, local pet expressions; never move the native window or hitbox."""

import math

from PySide6 import QtCore, QtGui


class PetExpression:
    DURATION = 1.25

    def __init__(self):
        self.kind = ""
        self.elapsed = self.DURATION
        self._last_start = float("-inf")

    def start(self, kind: str, now: float) -> bool:
        if kind not in {"stretch", "wiggle", "heart"} or now - self._last_start < 0.7:
            return False
        self.kind = kind
        self.elapsed = 0.0
        self._last_start = now
        return True

    def clear(self) -> None:
        self.kind = ""
        self.elapsed = self.DURATION

    def advance(self, dt: float) -> None:
        self.elapsed = min(self.DURATION, self.elapsed + max(0, dt))
        if self.elapsed >= self.DURATION:
            self.kind = ""

    def transform(self, painter: QtGui.QPainter, foot: QtCore.QPoint) -> None:
        if not self.kind:
            return
        progress = self.elapsed / self.DURATION
        wave = math.sin(math.pi * progress)
        painter.translate(foot)
        if self.kind == "wiggle":
            painter.rotate(2 * math.sin(4 * math.pi * progress) * wave)
        else:
            painter.scale(1 - 0.025 * wave, 1 + 0.025 * wave)
        painter.translate(-foot)

    def paint_decoration(self, painter: QtGui.QPainter, contact: QtCore.QRect) -> None:
        if self.kind != "heart":
            return
        progress = self.elapsed / self.DURATION
        size = min(24.0, contact.width() / 6, contact.height() / 6)
        # Stay inside the sprite's existing visible rectangle, including edges.
        x = contact.center().x()
        y = contact.top() + size * 1.8 - size * 0.5 * progress
        painter.save()
        painter.setOpacity(math.sin(math.pi * min(1, progress + 0.12)))
        painter.translate(x, y)
        painter.scale(size, size)
        path = QtGui.QPainterPath(QtCore.QPointF(0, 0.8))
        path.cubicTo(-1.6, -0.1, -0.8, -1.2, 0, -0.5)
        path.cubicTo(0.8, -1.2, 1.6, -0.1, 0, 0.8)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#ef6b9b"))
        painter.drawPath(path)
        painter.restore()
