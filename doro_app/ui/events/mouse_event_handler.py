"""Mouse event handler for DoroWindow."""

from __future__ import annotations

from PySide6 import QtCore, QtGui


class MouseEventHandler(QtCore.QObject):
    """
    Handles all mouse events for the Doro window.

    This class decouples mouse event handling from the window,
    using signals to communicate actions instead of direct window manipulation.

    Signals:
        window_drag_requested: Emitted when window should be moved (with delta position)
        drag_started: Emitted once per gesture when movement first exceeds
            the click/drag threshold — wired by the app to cancel any
            in-flight movement + queued click so dragging Doro mid-walk
            doesn't fire an unwanted click at the end.
        click_detected: Emitted when a click (not drag) is detected
        user_activity_detected: Emitted when any user interaction occurs
    """

    # Signals
    window_drag_requested = QtCore.Signal(QtCore.QPoint)  # global position for window
    drag_started = QtCore.Signal()
    click_detected = QtCore.Signal()
    user_activity_detected = QtCore.Signal()

    def __init__(self, click_threshold: int = 5):
        """
        Initialize mouse event handler.

        Args:
            click_threshold: Minimum movement distance to count as drag (pixels)
        """
        super().__init__()
        self._click_threshold = click_threshold

        # Internal state
        self._drag_pos: QtCore.QPoint | None = None
        self._click_press_pos: QtCore.QPointF | None = None
        self._click_was_dragging = False

    def handle_press(self, event: QtGui.QMouseEvent, frame_geometry: QtCore.QRect) -> bool:
        """
        Handle mouse press event.

        Args:
            event: Mouse event
            frame_geometry: Current window frame geometry

        Returns:
            True if event was handled, False to pass to parent
        """
        self.user_activity_detected.emit()

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Start window drag
            self._drag_pos = event.globalPosition().toPoint() - frame_geometry.topLeft()
            self._click_press_pos = event.position()
            self._click_was_dragging = False
            return True

        return False

    def handle_move(self, event: QtGui.QMouseEvent) -> bool:
        """
        Handle mouse move event.

        Args:
            event: Mouse event

        Returns:
            True if event was handled, False to pass to parent
        """
        # Track user activity if dragging
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.user_activity_detected.emit()

        # Handle window drag
        if self._drag_pos is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            # Check if movement exceeds click threshold
            if (
                self._click_press_pos is not None
                and not self._click_was_dragging
                and (event.position() - self._click_press_pos).manhattanLength() > self._click_threshold
            ):
                self._click_was_dragging = True
                # One-shot: fires only on the false→true transition so
                # downstream cancel handlers run once per drag gesture.
                self.drag_started.emit()

            # Emit drag request
            self.window_drag_requested.emit(event.globalPosition().toPoint() - self._drag_pos)
            return True

        return False

    def handle_release(self, event: QtGui.QMouseEvent) -> tuple[bool, bool]:
        """
        Handle mouse release event.

        Args:
            event: Mouse event

        Returns:
            Tuple of (handled, was_click)
            - handled: True if event was handled
            - was_click: True if this was a click (not drag)
        """
        self.user_activity_detected.emit()

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Check if this was a click (not drag)
            was_click = (
                not self._click_was_dragging
                and self._click_press_pos is not None
                and (event.position() - self._click_press_pos).manhattanLength() <= self._click_threshold
            )

            # Reset state
            self._drag_pos = None
            self._click_press_pos = None
            self._click_was_dragging = False

            # Emit click signal if detected
            if was_click:
                self.click_detected.emit()

            return (True, was_click)

        # Reset state for non-left button
        self._drag_pos = None
        self._click_press_pos = None
        self._click_was_dragging = False

        return (False, False)

    def handle_leave(self):
        """Handle mouse leave event."""

    def reset(self):
        """Reset internal state (e.g., when window loses focus)."""
        self._drag_pos = None
        self._click_press_pos = None
        self._click_was_dragging = False
