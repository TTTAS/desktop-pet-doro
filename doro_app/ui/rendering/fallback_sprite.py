"""Fallback sprite renderer for Doro when no GIF is available."""

from __future__ import annotations

from PySide6 import QtCore, QtGui

# ═══════════════════════════════════════════════════════════
# Private Module Constants - Fallback Sprite Geometry
# ═══════════════════════════════════════════════════════════
# These constants are internal to this module and define the
# geometry for drawing the fallback sprite when no GIF is loaded.

# Face outline path control points (cubic bezier)
_FACE_CENTER_X = 90
_FACE_CENTER_Y_TOP = 20
_FACE_CENTER_Y_BOTTOM = 160
_FACE_LEFT_X = 30
_FACE_RIGHT_X = 150
_FACE_CONTROL_X_LEFT = 50
_FACE_CONTROL_X_RIGHT = 130

# Blush (cheeks) positions and size
_BLUSH_LEFT_X = 55
_BLUSH_RIGHT_X = 107
_BLUSH_Y = 85
_BLUSH_WIDTH = 18
_BLUSH_HEIGHT = 10

# Eyes positions and size
_EYE_LEFT_X = 70
_EYE_RIGHT_X = 100
_EYE_Y = 70
_EYE_WIDTH = 10
_EYE_HEIGHT = 14

# Mouth path control points (smile curve)
_MOUTH_START_X = 80
_MOUTH_START_Y = 95
_MOUTH_CONTROL1_X = 90
_MOUTH_CONTROL1_Y = 105
_MOUTH_CONTROL2_X = 100
_MOUTH_CONTROL2_Y = 105
_MOUTH_END_X = 110
_MOUTH_END_Y = 95
_MOUTH_PEN_WIDTH = 2

# Styling
_DEFAULT_BORDER_COLOR = "#FF5C9ED6"
_DEFAULT_BORDER_WIDTH = 3


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
    painter.translate(-_FACE_CENTER_X, -_FACE_CENTER_X)

    # Draw face outline (rounded shape using cubic bezier curves)
    path = QtGui.QPainterPath(QtCore.QPointF(_FACE_CENTER_X, _FACE_CENTER_Y_TOP))
    path.cubicTo(_FACE_CONTROL_X_LEFT, _FACE_CENTER_Y_TOP, _FACE_LEFT_X, _FACE_CONTROL_X_LEFT, _FACE_LEFT_X, _FACE_CENTER_X)
    path.cubicTo(_FACE_LEFT_X, 130, _FACE_CONTROL_X_LEFT, _FACE_CENTER_Y_BOTTOM, _FACE_CENTER_X, _FACE_CENTER_Y_BOTTOM)
    path.cubicTo(_FACE_CONTROL_X_RIGHT, _FACE_CENTER_Y_BOTTOM, _FACE_RIGHT_X, 130, _FACE_RIGHT_X, _FACE_CENTER_X)
    path.cubicTo(_FACE_RIGHT_X, _FACE_CONTROL_X_LEFT, _FACE_CONTROL_X_RIGHT, _FACE_CENTER_Y_TOP, _FACE_CENTER_X, _FACE_CENTER_Y_TOP)

    # Create gradient fill for face
    fill = QtGui.QLinearGradient(
        QtCore.QPointF(_FACE_CENTER_X, _FACE_CENTER_Y_TOP),
        QtCore.QPointF(_FACE_CENTER_X, _FACE_CENTER_Y_BOTTOM)
    )
    fill.setColorAt(0.0, fill_colors[0])
    fill.setColorAt(0.4, fill_colors[1])
    fill.setColorAt(1.0, fill_colors[2])

    # Draw face with border and gradient fill
    painter.setPen(QtGui.QPen(QtGui.QColor(_DEFAULT_BORDER_COLOR), _DEFAULT_BORDER_WIDTH))
    painter.setBrush(QtGui.QBrush(fill))
    painter.drawPath(path)

    # Draw blush (cheeks) if visible
    if cheek_alpha > 0:
        blush = QtGui.QColor(blush_base_color)
        blush.setAlpha(int(cheek_alpha))
        painter.setBrush(blush)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QRectF(_BLUSH_LEFT_X, _BLUSH_Y, _BLUSH_WIDTH, _BLUSH_HEIGHT))
        painter.drawEllipse(QtCore.QRectF(_BLUSH_RIGHT_X, _BLUSH_Y, _BLUSH_WIDTH, _BLUSH_HEIGHT))

    # Draw eyes
    painter.setBrush(eye_color)
    painter.drawEllipse(QtCore.QRectF(_EYE_LEFT_X, _EYE_Y, _EYE_WIDTH, _EYE_HEIGHT))
    painter.drawEllipse(QtCore.QRectF(_EYE_RIGHT_X, _EYE_Y, _EYE_WIDTH, _EYE_HEIGHT))

    # Draw mouth (smile curve)
    _draw_mouth(painter)


def _draw_mouth(painter: QtGui.QPainter) -> None:
    """Draw the mouth curve for fallback sprite."""
    pen = QtGui.QPen(QtGui.QColor(51, 51, 51))
    pen.setWidthF(_MOUTH_PEN_WIDTH)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    mouth = QtGui.QPainterPath()
    mouth.moveTo(_MOUTH_START_X, _MOUTH_START_Y)
    mouth.cubicTo(_MOUTH_CONTROL1_X, _MOUTH_CONTROL1_Y, _MOUTH_CONTROL2_X, _MOUTH_CONTROL2_Y, _MOUTH_END_X, _MOUTH_END_Y)
    painter.drawPath(mouth)
