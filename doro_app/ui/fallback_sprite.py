"""Fallback sprite renderer for Doro when no GIF is available."""

from __future__ import annotations

from PySide6 import QtCore, QtGui

from ..constants import (
    # Face geometry
    FACE_CENTER_X, FACE_CENTER_Y_TOP, FACE_CENTER_Y_BOTTOM,
    FACE_LEFT_X, FACE_RIGHT_X, FACE_CONTROL_X_LEFT, FACE_CONTROL_X_RIGHT,
    # Blush geometry
    BLUSH_LEFT_X, BLUSH_RIGHT_X, BLUSH_Y, BLUSH_WIDTH, BLUSH_HEIGHT,
    # Eye geometry
    EYE_LEFT_X, EYE_RIGHT_X, EYE_Y, EYE_WIDTH, EYE_HEIGHT,
    # Mouth geometry
    MOUTH_START_X, MOUTH_START_Y, MOUTH_CONTROL1_X, MOUTH_CONTROL1_Y,
    MOUTH_CONTROL2_X, MOUTH_CONTROL2_Y, MOUTH_END_X, MOUTH_END_Y, MOUTH_PEN_WIDTH,
    # Styling
    DEFAULT_BORDER_COLOR, DEFAULT_BORDER_WIDTH,
)


def draw_fallback_sprite(
    painter: QtGui.QPainter,
    fill_colors: tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor],
    cheek_alpha: float,
    blush_base_color: QtGui.QColor,
    eye_color: QtGui.QColor,
) -> None:
    """
    Draw the fallback sprite when no GIF is available.

    Args:
        painter: QPainter to draw with (already transformed to sprite center)
        fill_colors: Three-color gradient for face (top, mid, bottom)
        cheek_alpha: Alpha value for blush (0-255)
        blush_base_color: Base color for blush
        eye_color: Color for eyes
    """
    # Translate to sprite coordinate system
    painter.translate(-FACE_CENTER_X, -FACE_CENTER_X)

    # Draw face outline (rounded shape using cubic bezier curves)
    path = QtGui.QPainterPath(QtCore.QPointF(FACE_CENTER_X, FACE_CENTER_Y_TOP))
    path.cubicTo(FACE_CONTROL_X_LEFT, FACE_CENTER_Y_TOP, FACE_LEFT_X, FACE_CONTROL_X_LEFT, FACE_LEFT_X, FACE_CENTER_X)
    path.cubicTo(FACE_LEFT_X, 130, FACE_CONTROL_X_LEFT, FACE_CENTER_Y_BOTTOM, FACE_CENTER_X, FACE_CENTER_Y_BOTTOM)
    path.cubicTo(FACE_CONTROL_X_RIGHT, FACE_CENTER_Y_BOTTOM, FACE_RIGHT_X, 130, FACE_RIGHT_X, FACE_CENTER_X)
    path.cubicTo(FACE_RIGHT_X, FACE_CONTROL_X_LEFT, FACE_CONTROL_X_RIGHT, FACE_CENTER_Y_TOP, FACE_CENTER_X, FACE_CENTER_Y_TOP)

    # Create gradient fill for face
    fill = QtGui.QLinearGradient(
        QtCore.QPointF(FACE_CENTER_X, FACE_CENTER_Y_TOP),
        QtCore.QPointF(FACE_CENTER_X, FACE_CENTER_Y_BOTTOM)
    )
    fill.setColorAt(0.0, fill_colors[0])
    fill.setColorAt(0.4, fill_colors[1])
    fill.setColorAt(1.0, fill_colors[2])

    # Draw face with border and gradient fill
    painter.setPen(QtGui.QPen(QtGui.QColor(DEFAULT_BORDER_COLOR), DEFAULT_BORDER_WIDTH))
    painter.setBrush(QtGui.QBrush(fill))
    painter.drawPath(path)

    # Draw blush (cheeks) if visible
    if cheek_alpha > 0:
        blush = QtGui.QColor(blush_base_color)
        blush.setAlpha(int(cheek_alpha))
        painter.setBrush(blush)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QRectF(BLUSH_LEFT_X, BLUSH_Y, BLUSH_WIDTH, BLUSH_HEIGHT))
        painter.drawEllipse(QtCore.QRectF(BLUSH_RIGHT_X, BLUSH_Y, BLUSH_WIDTH, BLUSH_HEIGHT))

    # Draw eyes
    painter.setBrush(eye_color)
    painter.drawEllipse(QtCore.QRectF(EYE_LEFT_X, EYE_Y, EYE_WIDTH, EYE_HEIGHT))
    painter.drawEllipse(QtCore.QRectF(EYE_RIGHT_X, EYE_Y, EYE_WIDTH, EYE_HEIGHT))

    # Draw mouth (smile curve)
    _draw_mouth(painter)


def _draw_mouth(painter: QtGui.QPainter) -> None:
    """Draw the mouth curve for fallback sprite."""
    pen = QtGui.QPen(QtGui.QColor(51, 51, 51))
    pen.setWidthF(MOUTH_PEN_WIDTH)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    mouth = QtGui.QPainterPath()
    mouth.moveTo(MOUTH_START_X, MOUTH_START_Y)
    mouth.cubicTo(MOUTH_CONTROL1_X, MOUTH_CONTROL1_Y, MOUTH_CONTROL2_X, MOUTH_CONTROL2_Y, MOUTH_END_X, MOUTH_END_Y)
    painter.drawPath(mouth)
