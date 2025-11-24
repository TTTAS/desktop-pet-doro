"""Window layout and positioning utilities.

Pure functions for calculating window positions, sizes, and screen geometry.
No dependencies on window state - all inputs are explicit parameters.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class WindowLayoutManager:
    """
    Static utility class for window layout calculations.

    All methods are pure functions (no side effects, no instance state).
    This makes them easy to test without needing Qt widget instances.
    """

    @staticmethod
    def get_available_screen_geometry(window: QtWidgets.QWidget | None = None) -> QtCore.QRect:
        """
        Get the available screen geometry for a window.

        Args:
            window: The widget to get screen geometry for. If None, uses primary screen.

        Returns:
            Available screen geometry (excluding taskbars, etc.)
            Falls back to 1920x1080 if no screen is found.
        """
        screen = None

        if window:
            handle = window.windowHandle()
            if handle:
                screen = handle.screen()

        if not screen:
            screen = QtWidgets.QApplication.primaryScreen()

        if screen:
            return screen.availableGeometry()

        # Fallback if no screen found
        return QtCore.QRect(0, 0, 1920, 1080)

    @staticmethod
    def clamp_position(
        desired: QtCore.QPoint,
        window_size: QtCore.QSize,
        screen_rect: QtCore.QRect,
    ) -> QtCore.QPoint:
        """
        Clamp window position to stay within screen bounds.

        Args:
            desired: Desired window position (top-left corner)
            window_size: Size of the window
            screen_rect: Available screen geometry

        Returns:
            Clamped position that keeps window visible on screen
        """
        # Calculate bounds
        max_x = screen_rect.left() + max(0, screen_rect.width() - window_size.width())
        max_y = screen_rect.top() + max(0, screen_rect.height() - window_size.height())
        min_x = screen_rect.left()
        min_y = screen_rect.top()

        # Clamp to bounds
        clamped_x = max(min_x, min(max_x, desired.x()))
        clamped_y = max(min_y, min(max_y, desired.y()))

        return QtCore.QPoint(clamped_x, clamped_y)

    @staticmethod
    def compute_panel_size_hint(
        sprite_size: QtCore.QSize,
        bubble_text: str,
    ) -> tuple[float, float]:
        """
        Compute suggested panel size based on sprite and text content.

        Args:
            sprite_size: Size of the sprite
            bubble_text: Text to display in bubble (may be empty)

        Returns:
            Tuple of (panel_width, panel_height) in pixels
        """
        text = bubble_text.strip()
        sprite_w = max(120.0, float(sprite_size.width()))
        panel_width = max(160.0, sprite_w)
        available_text_width = max(80.0, panel_width - 56.0)

        # Calculate text height
        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.Bold)
        metrics = QtGui.QFontMetrics(font)

        if text:
            flags = int(
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
            )
            flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
            text_rect = metrics.boundingRect(
                QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
                flags,
                text,
            )
            text_height = float(text_rect.height())
        else:
            text_height = float(metrics.lineSpacing())

        panel_height = max(80.0, text_height + 56.0)
        return panel_width, panel_height
