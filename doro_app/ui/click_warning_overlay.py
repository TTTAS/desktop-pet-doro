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

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.automation.coordinates import compute_logical_point_from_physical
from ..utils.logger import get_logger

logger = get_logger(__name__)


_BORDER_COLOR = QtGui.QColor(220, 30, 30)
_FILL_COLOR = QtGui.QColor(220, 30, 30, 40)  # ~16% red wash so the frame is visible
_BORDER_WIDTH_PX = 4


class ClickWarningOverlay(QtWidgets.QWidget):
    """Frameless click-through window that paints a red border around the
    a11y element Doro is about to click."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowTransparentForInput
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

    def set_bounds_and_show(
        self,
        bounds_physical: tuple[int, int, int, int],
        host_window: QtWidgets.QWidget,
    ) -> None:
        """Place the overlay over ``bounds_physical`` (a11y physical pixels)
        and show it. Single-screen scope: uses ``host_window``'s screen for
        origin/DPR; cross-monitor targets will be misplaced (out of scope).
        """
        screen = host_window.screen() or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            logger.warning("warning-frame: no screen available, skipping")
            return
        geom = screen.geometry()
        dpr = screen.devicePixelRatio() or 1.0

        x_phys, y_phys, w_phys, h_phys = bounds_physical
        lx, ly = compute_logical_point_from_physical(
            (x_phys, y_phys),
            screen_origin_logical=(geom.x(), geom.y()),
            device_pixel_ratio=dpr,
        )
        import sys

        if sys.platform == "darwin":
            lw, lh = int(w_phys), int(h_phys)
        else:
            lw = max(1, round(w_phys / dpr))
            lh = max(1, round(h_phys / dpr))

        logger.debug(
            f"warning-frame phys{bounds_physical} → logical=({lx},{ly} {lw}x{lh}) dpr={dpr}"
        )

        # Order matters on Windows: show first so a native handle gets
        # created on the right screen, then setGeometry, then raise/update.
        self.setGeometry(lx, ly, lw, lh)
        if not self.isVisible():
            self.show()
        else:
            # Already visible from a prior wind-up — make sure geometry sticks.
            self.setGeometry(lx, ly, lw, lh)
        self.raise_()
        self.update()

    def hide_and_clear(self) -> None:
        self.hide()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        # Semi-transparent fill makes the frame visible even when the border
        # falls on top of a same-colour element edge.
        painter.fillRect(self.rect(), _FILL_COLOR)
        pen = QtGui.QPen(_BORDER_COLOR, _BORDER_WIDTH_PX)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        # Inset by half the pen width so the stroke stays inside the widget.
        inset = _BORDER_WIDTH_PX // 2
        painter.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))
        painter.end()
