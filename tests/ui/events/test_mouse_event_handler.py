"""Tests for MouseEventHandler drag/click signal semantics."""

from __future__ import annotations

from PySide6 import QtCore

from doro_app.ui.events.mouse_event_handler import MouseEventHandler


LEFT = QtCore.Qt.MouseButton.LeftButton
NO_BUTTON = QtCore.Qt.MouseButton.NoButton


class _Evt:
    """Minimal stand-in for QMouseEvent covering the handler's reads."""

    def __init__(self, *, button=NO_BUTTON, buttons=NO_BUTTON, pos=(0, 0), gpos=(0, 0)):
        self._button = button
        self._buttons = buttons
        self._pos = QtCore.QPointF(*pos)
        self._g = QtCore.QPointF(*gpos)

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def position(self):
        return self._pos

    def globalPosition(self):
        return self._g


def _make_handler(recorder):
    handler = MouseEventHandler(click_threshold=5)
    handler.drag_started.connect(lambda: recorder.append("drag_started"))
    handler.drag_ended.connect(lambda: recorder.append("drag_ended"))
    handler.click_detected.connect(lambda: recorder.append("click"))
    return handler


FRAME = QtCore.QRect(0, 0, 50, 50)


def test_click_emits_click_not_drag_ended(qtbot):
    events: list[str] = []
    handler = _make_handler(events)

    handler.handle_press(_Evt(button=LEFT, pos=(10, 10), gpos=(100, 100)), FRAME)
    # Tiny move within threshold, then release.
    handler.handle_move(_Evt(buttons=LEFT, pos=(11, 11), gpos=(101, 101)))
    handler.handle_release(_Evt(button=LEFT, pos=(11, 11), gpos=(101, 101)))

    assert events == ["click"]


def test_drag_emits_started_then_ended_no_click(qtbot):
    events: list[str] = []
    handler = _make_handler(events)

    handler.handle_press(_Evt(button=LEFT, pos=(10, 10), gpos=(100, 100)), FRAME)
    # Move past the threshold -> drag_started (one-shot).
    handler.handle_move(_Evt(buttons=LEFT, pos=(40, 40), gpos=(130, 130)))
    # Further movement must not re-emit drag_started.
    handler.handle_move(_Evt(buttons=LEFT, pos=(45, 45), gpos=(135, 135)))
    handler.handle_release(_Evt(button=LEFT, pos=(45, 45), gpos=(135, 135)))

    assert events == ["drag_started", "drag_ended"]


def test_release_without_press_is_noop(qtbot):
    events: list[str] = []
    handler = _make_handler(events)

    # Release with no prior drag gesture: neither click nor drag_ended.
    handler.handle_release(_Evt(button=LEFT, pos=(10, 10), gpos=(100, 100)))

    assert events == []
