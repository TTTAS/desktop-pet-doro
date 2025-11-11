"""Doro-themed context menu with custom styling and avatar decoration."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class DoroMenu(QtWidgets.QMenu):
    """
    Custom context menu with Doro theme.

    Features:
    - Pink color scheme matching Doro's hair color (#FF9BE3FF)
    - Optional Doro avatar in corner
    - Smooth gradients and rounded corners
    - Custom styling for all menu elements
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, avatar_position: str = "top-right"):
        """
        Initialize Doro-themed menu.

        Args:
            parent: Parent widget
            avatar_position: Where to place avatar - "top-left", "top-right", or "none"
        """
        super().__init__(parent)
        self._avatar_position = avatar_position
        self._avatar_pixmap: QtGui.QPixmap | None = None
        self._avatar_size = 48

        # Apply Doro theme stylesheet
        self._apply_doro_stylesheet()

    def set_avatar(self, pixmap: QtGui.QPixmap | None):
        """Set the avatar pixmap to display in corner."""
        self._avatar_pixmap = pixmap
        self.update()

    def _apply_doro_stylesheet(self):
        """Apply pink-themed stylesheet matching Doro's colors."""
        # Doro color palette
        doro_pink = "#FF9BE3"      # Main hair color
        doro_light_pink = "#FFC4F0"  # Lighter shade
        doro_dark_pink = "#E86BD1"   # Darker shade
        doro_accent = "#6CC1F0"      # Blue accent from gradient

        stylesheet = f"""
        QMenu {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF,
                stop:0.05 #FFF5FC,
                stop:1 #FFE8F7
            );
            border: 2px solid {doro_pink};
            border-radius: 12px;
            padding: 8px 4px;
            margin: 0px;
        }}

        QMenu::item {{
            background-color: transparent;
            padding: 8px 32px 8px 16px;
            margin: 2px 6px;
            border-radius: 6px;
            color: #2D2D2D;
            font-size: 11pt;
        }}

        QMenu::item:selected {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {doro_light_pink},
                stop:1 {doro_pink}
            );
            color: white;
            font-weight: 600;
        }}

        QMenu::item:disabled {{
            color: #AAAAAA;
            background-color: transparent;
        }}

        QMenu::separator {{
            height: 2px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent,
                stop:0.4 {doro_pink},
                stop:0.6 {doro_pink},
                stop:1 transparent
            );
            margin: 6px 16px;
        }}

        QMenu::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 3px;
            margin-left: 6px;
        }}

        QMenu::indicator:non-exclusive:checked {{
            background-color: {doro_pink};
            border: 2px solid {doro_dark_pink};
            image: url(none);
        }}

        QMenu::right-arrow {{
            width: 12px;
            height: 12px;
            margin-right: 8px;
        }}
        """

        self.setStyleSheet(stylesheet)

        # Note: Removed FramelessWindowHint and WA_TranslucentBackground
        # These caused "UpdateLayeredWindowIndirect failed" errors on Windows
        # The pink theme and rounded corners are preserved via stylesheet

    def paintEvent(self, event: QtGui.QPaintEvent):
        """Custom paint event to draw avatar and enhanced styling."""
        # First, let Qt draw the standard menu
        super().paintEvent(event)

        # Then draw our custom decorations
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Draw avatar if available
        if self._avatar_pixmap and not self._avatar_pixmap.isNull() and self._avatar_position != "none":
            self._draw_avatar(painter)

        # Draw corner accent
        self._draw_corner_accent(painter)

    def _draw_avatar(self, painter: QtGui.QPainter):
        """Draw Doro avatar in the specified corner."""
        size = self._avatar_size
        margin = 8

        # Calculate position based on avatar_position
        if self._avatar_position == "top-right":
            x = self.width() - size - margin
            y = margin
        elif self._avatar_position == "top-left":
            x = margin
            y = margin
        else:
            return

        # Create rounded rect path for avatar
        avatar_rect = QtCore.QRectF(x, y, size, size)
        path = QtGui.QPainterPath()
        path.addRoundedRect(avatar_rect, size / 2, size / 2)

        # Draw pink glow behind avatar
        painter.save()
        glow_rect = avatar_rect.adjusted(-3, -3, 3, 3)
        glow_path = QtGui.QPainterPath()
        glow_path.addRoundedRect(glow_rect, (size + 6) / 2, (size + 6) / 2)

        glow_gradient = QtGui.QRadialGradient(
            glow_rect.center(),
            size / 2 + 6
        )
        glow_gradient.setColorAt(0, QtGui.QColor(255, 155, 227, 120))
        glow_gradient.setColorAt(1, QtGui.QColor(255, 155, 227, 0))
        painter.fillPath(glow_path, glow_gradient)
        painter.restore()

        # Draw white border
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 3))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

        # Draw avatar with clipping
        painter.save()
        painter.setClipPath(path)
        scaled_pixmap = self._avatar_pixmap.scaled(
            int(size), int(size),
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(int(x), int(y), scaled_pixmap)
        painter.restore()

    def _draw_corner_accent(self, painter: QtGui.QPainter):
        """Draw decorative accent in opposite corner from avatar."""
        # Determine which corner to decorate
        if self._avatar_position == "top-right":
            # Draw accent in bottom-left
            x, y = 8, self.height() - 8
            angle_start = 180
        elif self._avatar_position == "top-left":
            # Draw accent in bottom-right
            x, y = self.width() - 8, self.height() - 8
            angle_start = 0
        else:
            # No avatar, draw in top-right
            x, y = self.width() - 8, 8
            angle_start = 0

        # Draw small decorative arc
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        gradient = QtGui.QRadialGradient(x, y, 20)
        gradient.setColorAt(0, QtGui.QColor(255, 155, 227, 60))
        gradient.setColorAt(1, QtGui.QColor(255, 155, 227, 0))

        painter.setBrush(gradient)
        painter.drawEllipse(QtCore.QPointF(x, y), 20, 20)
        painter.restore()

    # Note: Removed showEvent with QGraphicsDropShadowEffect
    # This caused rendering conflicts with the custom paintEvent on Windows
    # The menu still looks good with just the stylesheet and avatar decoration


def create_doro_menu(
    parent: QtWidgets.QWidget | None = None,
    avatar_position: str = "top-right",
    gif_movie: QtGui.QMovie | None = None
) -> DoroMenu:
    """
    Create a Doro-themed menu with optional avatar.

    Args:
        parent: Parent widget
        avatar_position: "top-left", "top-right", or "none"
        gif_movie: QMovie to extract first frame as avatar

    Returns:
        Configured DoroMenu instance
    """
    menu = DoroMenu(parent, avatar_position=avatar_position)

    # Extract first frame from GIF if available
    if gif_movie and gif_movie.isValid():
        # Temporarily jump to first frame to get avatar
        current_frame = gif_movie.currentFrameNumber()
        gif_movie.jumpToFrame(0)
        first_frame_pixmap = gif_movie.currentPixmap()

        # Restore to current frame (to avoid disrupting animation)
        if current_frame >= 0:
            gif_movie.jumpToFrame(current_frame)

        if not first_frame_pixmap.isNull():
            menu.set_avatar(first_frame_pixmap)

    return menu
