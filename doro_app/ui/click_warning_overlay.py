"""Red warning frame shown during the 1.5s click wind-up.

Implements :class:`ClickWarningOverlayPort` (Qt side). When the
AutomationManager starts a click wind-up, it calls ``begin(bounds)`` with
the physical-pixel bounds of the a11y element the click will land on; the
overlay translates those into Qt logical coordinates, sizes a frameless
transparent click-through window to the rect, and paints a red border on
top. ``end()`` hides it again.

The overlay never intercepts input (``Qt.WindowTransparentForInput``) — it
is purely a visual cue so the user can confirm the target during the
Esc-cancel window.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.automation.coordinates import compute_logical_point_from_physical


_BORDER_COLOR = QtGui.QColor(220, 30, 30)
_BORDER_WIDTH_PX = 3


class ClickWarningOverlay(QtWidgets.QWidget):
    """Frameless click-through window that paints a red border."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.hide()

    def set_bounds_and_show(
        self,
        bounds_physical: tuple[int, int, int, int],
        host_window: QtWidgets.QWidget,
    ) -> None:
        """Place the overlay over ``bounds_physical`` (a11y physical pixels)
        and show it.

        Uses ``host_window``'s screen for the origin/DPR conversion. Single-
        screen scope: when the target element lives on a different monitor
        than Doro, the placement will be wrong (out of scope for now).
        """
        screen = host_window.screen() or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.geometry()
        dpr = screen.devicePixelRatio() or 1.0

        x_phys, y_phys, w_phys, h_phys = bounds_physical
        lx, ly = compute_logical_point_from_physical(
            (x_phys, y_phys),
            screen_origin_logical=(geom.x(), geom.y()),
            device_pixel_ratio=dpr,
        )
        # macOS path returns physical points unchanged; widths/heights must
        # match that. Mirror the helper's branch.
        import sys
        if sys.platform == "darwin":
            lw, lh = int(w_phys), int(h_phys)
        else:
            lw = max(1, round(w_phys / dpr))
            lh = max(1, round(h_phys / dpr))

        self.setGeometry(lx, ly, lw, lh)
        self.show()
        self.raise_()

    def hide_and_clear(self) -> None:
        self.hide()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(_BORDER_COLOR, _BORDER_WIDTH_PX)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        # Inset by half the pen width so the stroke stays inside the widget.
        inset = _BORDER_WIDTH_PX // 2
        painter.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))
        painter.end()
