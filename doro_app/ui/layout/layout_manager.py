"""Window layout and positioning utilities.

Pure functions for calculating window positions, sizes, and screen geometry.
No dependencies on window state - all inputs are explicit parameters.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...constants import FALLBACK_SCREEN_HEIGHT, FALLBACK_SCREEN_WIDTH


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
        return QtCore.QRect(0, 0, FALLBACK_SCREEN_WIDTH, FALLBACK_SCREEN_HEIGHT)

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
    def clamp_sprite_position(
        desired: QtCore.QPoint, sprite_rect: QtCore.QRect, screen_rect: QtCore.QRect
    ) -> QtCore.QPoint:
        """Keep the character visible; transparent panel reserve is not a wall."""
        visible_top_left = desired + sprite_rect.topLeft()
        return (
            WindowLayoutManager.clamp_position(visible_top_left, sprite_rect.size(), screen_rect)
            - sprite_rect.topLeft()
        )

    @staticmethod
    def compute_preferred_window_size(sprite_size: QtCore.QSize) -> tuple[int, int]:
        """Window size for a sprite: the sprite itself (at least 120×120).

        The speech bubble has its own window (SpeechBubbleWindow), so Doro's
        window never reserves room for it.
        """
        return (
            round(max(120.0, float(sprite_size.width()))),
            round(max(120.0, float(sprite_size.height()))),
        )

    @staticmethod
    def apply_window_preferred_size(window: QtWidgets.QWidget, sprite_size: QtCore.QSize) -> None:
        """Resize ``window`` (and its minimum size) to fit ``sprite_size``."""
        desired_w, desired_h = WindowLayoutManager.compute_preferred_window_size(sprite_size)
        min_size = window.minimumSize()
        if min_size.width() != desired_w or min_size.height() != desired_h:
            window.setMinimumSize(desired_w, desired_h)
        if window.width() != desired_w or window.height() != desired_h:
            window.resize(desired_w, desired_h)
            window.update()

    @staticmethod
    def move_window_safely(window: QtWidgets.QWidget, point: QtCore.QPoint):
        """
        Move window to specified position safely.

        This method has side effects - it moves the window.
        Handles edge cases like invalid point, same position, and window handle.

        Args:
            window: Window to move
            point: Target position (top-left corner)
        """
        if not isinstance(point, QtCore.QPoint):
            return

        current = window.frameGeometry().topLeft()
        if current == point:
            return

        # Try using window handle for more reliable positioning
        handle = window.windowHandle()
        if handle is not None:
            try:
                handle.setPosition(point)
            except Exception:
                pass

        # Fallback to regular move
        window.move(point)

        # Let the normal event loop paint. Pumping it here can recursively run
        # movement timers; raising on every step also defeats "not topmost".

    @staticmethod
    def extract_sprite_size_from_movie(movie: QtGui.QMovie | None) -> QtCore.QSize | None:
        """
        Extract sprite size from QMovie.

        Args:
            movie: QMovie to extract size from (or None)

        Returns:
            Sprite size if movie is valid, None otherwise
        """
        if movie and movie.isValid():
            rect = movie.frameRect()
            if rect.width() > 0 and rect.height() > 0:
                return rect.size()
        return None
