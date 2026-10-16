"""Doro's speech bubble in its own small window.

The bubble used to be painted inside Doro's window, which therefore grew from
the sprite size to ~640×460 whenever Doro spoke and shrank back afterwards.
Each change was resize-then-move, and Windows could paint in between: Doro
seemed to teleport away and back. Now Doro's window always stays sprite-sized
and this window follows it (see docs/speech-bubble-window-plan.md).

- Above Doro by default; below only when there is not enough room above.
- Width follows the text, between BUBBLE_MIN_WIDTH and BUBBLE_MAX_WIDTH.
- Transparent for input: clicking the bubble clicks whatever is behind it.
- Owned by Doro's window, so Windows keeps it stacked above Doro.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ...constants import COLOR_ALPHA_MAX
from ..rendering.design_tokens import tokens
from ..rendering.rendering_engine import RenderingEngine

BUBBLE_MIN_WIDTH = 120
BUBBLE_MAX_WIDTH = 280
BUBBLE_GAP = 12  # between Doro's visible body and the bubble
BUBBLE_SCREEN_MARGIN = 8  # keep the bubble this far inside the work area
WINDOW_PADDING = 14  # transparent room around the panel for its shadow and outline

_TEXT_FLAGS = (
    QtCore.Qt.AlignmentFlag.AlignLeft
    | QtCore.Qt.AlignmentFlag.AlignTop
    | QtCore.Qt.TextFlag.TextWordWrap
    | QtCore.Qt.TextFlag.TextWrapAnywhere
)


def bubble_panel_size(text: str, font: QtGui.QFont) -> QtCore.QSize:
    """Panel size for ``text``: as wide as its longest line, within the min/max width."""
    metrics = QtGui.QFontMetrics(font)
    pad_x = round(tokens.spacing.bubble_inner_x)
    pad_y = round(tokens.spacing.bubble_inner_y)
    longest = max((metrics.horizontalAdvance(line) for line in text.splitlines()), default=0)
    width = max(BUBBLE_MIN_WIDTH, min(BUBBLE_MAX_WIDTH, longest + 2 * pad_x + 2))
    wrapped = metrics.boundingRect(
        QtCore.QRect(0, 0, width - 2 * pad_x, 100_000), int(_TEXT_FLAGS), text
    )
    height = max(metrics.lineSpacing(), wrapped.height()) + 2 * pad_y
    return QtCore.QSize(width, height)


def place_bubble(
    body: QtCore.QRect, size: QtCore.QSize, area: QtCore.QRect
) -> tuple[QtCore.QRect, bool]:
    """Where the panel goes on screen, and whether it sits above ``body``.

    ``body`` is Doro's visible character rectangle and ``area`` the work area of
    the screen she is on, both in screen coordinates.
    """
    top_limit = area.top() + BUBBLE_SCREEN_MARGIN
    bottom_limit = area.bottom() - BUBBLE_SCREEN_MARGIN
    room_above = body.top() - BUBBLE_GAP - top_limit
    room_below = bottom_limit - (body.bottom() + BUBBLE_GAP)
    above = room_above >= size.height() or room_above >= room_below

    if above:
        top = max(top_limit, body.top() - BUBBLE_GAP - size.height())
    else:
        top = min(body.bottom() + BUBBLE_GAP, bottom_limit - size.height())

    left = body.left() + (body.width() - size.width()) // 2
    left_limit = area.left() + BUBBLE_SCREEN_MARGIN
    right_limit = area.right() - BUBBLE_SCREEN_MARGIN - size.width()
    left = max(left_limit, min(right_limit, left)) if left_limit <= right_limit else left_limit
    return QtCore.QRect(QtCore.QPoint(left, top), size), above


class SpeechBubbleWindow(QtWidgets.QWidget):
    def __init__(
        self,
        view_model,
        bubble_controller,
        body_on_screen: Callable[[], QtCore.QRect],
        work_area: Callable[[], QtCore.QRect],
        parent: QtWidgets.QWidget | None = None,
        *,
        stay_on_top: bool = True,
    ) -> None:
        super().__init__(parent)
        flags = (
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowTransparentForInput
            | QtCore.Qt.WindowType.NoDropShadowWindowHint
        )
        if stay_on_top:  # matches Doro's own --not-topmost choice
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowTitle("Doro · 對話泡泡")
        self._view_model = view_model
        self._bubble = bubble_controller
        self._body_on_screen = body_on_screen
        self._work_area = work_area
        self._engine = RenderingEngine(view_model)
        self._text = ""
        self._above = True
        self._suppressed = False

    # ------------------------------------------------------------- state
    @property
    def above(self) -> bool:
        return self._above

    def panel_geometry(self) -> QtCore.QRect:
        """The visible bubble on screen (the window adds transparent shadow room)."""
        return self.geometry().adjusted(
            WINDOW_PADDING, WINDOW_PADDING, -WINDOW_PADDING, -WINDOW_PADDING
        )

    def set_suppressed(self, suppressed: bool) -> None:
        """Hide while the chat history is expanded (it already shows the same line)."""
        self._suppressed = bool(suppressed)
        self.refresh()

    def _wanted_text(self) -> str:
        text = (self._bubble.text or "").strip()
        shown = self._view_model.bubble_visible or self._bubble.text_show_override
        if not text or not shown or self._view_model.bubble_alpha <= 0 or self._suppressed:
            return ""
        owner = self.parentWidget()
        if owner is not None and not owner.isVisible():
            return ""
        return text

    # ---------------------------------------------------------- layout
    def refresh(self) -> None:
        """Re-read the text and visibility, then show, hide or re-layout."""
        text = self._wanted_text()
        if not text:
            self._text = ""
            self.hide()
            return
        changed = text != self._text
        self._text = text
        self.follow()
        if not self.isVisible():
            self.show()
            self.raise_()
        elif changed:
            self.update()

    def follow(self) -> None:
        """Re-position next to Doro; call whenever her window moves or resizes."""
        if not self._text:
            return
        size = bubble_panel_size(self._text, self._engine.panel_font)
        panel, above = place_bubble(self._body_on_screen(), size, self._work_area())
        self._above = above
        self._view_model.set_bubble_side("above" if above else "below")
        geometry = panel.adjusted(-WINDOW_PADDING, -WINDOW_PADDING, WINDOW_PADDING, WINDOW_PADDING)
        if geometry != self.geometry():
            self.setGeometry(geometry)
            self.update()

    # ---------------------------------------------------------- painting
    def paintEvent(self, _event) -> None:
        if not self._text:
            return
        painter = QtGui.QPainter(self)
        alpha = min(max(int(self._view_model.bubble_alpha), 0), COLOR_ALPHA_MAX)
        panel = QtCore.QRectF(self.rect()).adjusted(
            WINDOW_PADDING, WINDOW_PADDING, -WINDOW_PADDING, -WINDOW_PADDING
        )
        self._engine.draw_bubble(painter, panel, self._text, alpha, below=not self._above)
        painter.end()
