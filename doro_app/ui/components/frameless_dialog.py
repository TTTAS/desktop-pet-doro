"""Frameless dialog base class with custom title bar."""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class _TitleBar(QtWidgets.QWidget):
    """Custom title bar with drag support and close button."""

    def __init__(self, title: str, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self._parent_dialog = parent
        self._drag_pos: Optional[QtCore.QPoint] = None
        self.setFixedHeight(36)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(8)

        # Title text
        self._title_label = QtWidgets.QLabel(title)
        self._title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #4a2040; background: transparent;"
        )
        layout.addWidget(self._title_label)

        layout.addStretch()

        # Close button
        close_btn = QtWidgets.QPushButton("\u2715")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: #e8609c; color: white; border: none; "
            "border-radius: 12px; font-size: 13px; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background: #db2777; }"
        )
        close_btn.clicked.connect(parent.close)
        layout.addWidget(close_btn)

    def set_title(self, title: str):
        self._title_label.setText(title)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent_dialog.pos()
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._drag_pos is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._parent_dialog.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        self._drag_pos = None


class FramelessDialog(QtWidgets.QDialog):
    """
    QDialog without native window frame.

    Features:
    - No native title bar or window border
    - Translucent background with rounded corners
    - Custom title bar with drag-to-move and close button
    - Drop shadow painted around the content

    Subclasses should add their content to self.content_layout.
    """

    def __init__(self, title: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Dialog
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Outer layout (holds the painted card)
        self._outer_layout = QtWidgets.QVBoxLayout(self)
        self._outer_layout.setContentsMargins(12, 12, 12, 12)  # space for shadow
        self._outer_layout.setSpacing(0)

        # Card container (the visible rounded rect)
        self._card = QtWidgets.QWidget()
        self._card.setObjectName("framelessCard")
        self._card.setStyleSheet(
            "#framelessCard { background: #fff0f6; border-radius: 16px; "
            "border: 1px solid rgba(232, 96, 156, 0.35); }"
        )
        card_layout = QtWidgets.QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar
        self._title_bar = _TitleBar(title, self)
        card_layout.addWidget(self._title_bar)

        # Content area
        self._content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        self.content_layout.setContentsMargins(20, 10, 20, 20)
        self.content_layout.setSpacing(14)
        card_layout.addWidget(self._content_widget, 1)

        self._outer_layout.addWidget(self._card)

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        self._title_bar.set_title(title)

    def paintEvent(self, event: QtGui.QPaintEvent):
        """Paint drop shadow behind the card."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Draw shadow layers
        shadow_color = QtGui.QColor(100, 50, 80, 25)
        for i in range(6):
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(shadow_color)
            rect = self._card.geometry().adjusted(-i, -i, i, i)
            painter.drawRoundedRect(rect, 16 + i, 16 + i)

        painter.end()
