"""Bubble (speech panel) controller for the Doro window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from .window import DoroWindow


@dataclass
class BubbleConfig:
    offset_x: float = 120.0
    offset_y: float = -110.0
    scale: float = 1.0
    auto_hide_ms: int = 6000


class BubbleController:
    """Encapsulates bubble offset/scale storage and drag interactions."""

    def __init__(self, window: DoroWindow):
        self._window = window
        self._offset = QtCore.QPointF(0.0, 0.0)
        self._scale = 1.0
        self._dragging = False
        self._resizing = False
        self._drag_start: QtCore.QPointF | None = None
        self._initial_offset = QtCore.QPointF(0.0, 0.0)
        self._resize_start: QtCore.QPointF | None = None
        self._resize_anchor: QtCore.QPointF | None = None
        self._initial_scale = 1.0
        self._resize_cursor_active = False
        self._hide_timer = QtCore.QTimer(window)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.clear_text)
        # expose timer for legacy references
        window._bubble_hide_timer = self._hide_timer

    # ------------------------------------------------------------------ State access
    @property
    def offset(self) -> QtCore.QPointF:
        return QtCore.QPointF(self._offset)

    @property
    def scale(self) -> float:
        return float(self._scale)

    def apply_persisted_config(self, config: BubbleConfig):
        self.apply_offset(QtCore.QPointF(config.offset_x, config.offset_y), persist=False)
        self.set_scale(config.scale, persist=False)

    def clamp_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        return self._clamp_offset(candidate)

    def clamp_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        return self._clamp_offset(candidate)

    # ------------------------------------------------------------------ Offset/scale manipulation
    def apply_offset(self, candidate: QtCore.QPointF, *, persist: bool = False):
        window = self._window
        self._offset = self.clamp_offset(candidate)
        window._bubble_offset = QtCore.QPointF(self._offset)
        window._update_bubble_side_from_offset()
        if persist:
            self._persist_preferences()
        window.update()

    def set_scale(self, value: float, *, persist: bool = False):
        window = self._window
        self._scale = max(0.5, min(2.0, float(value)))
        window._bubble_scale = self._scale
        if persist:
            self._persist_preferences()
        window.update()

    def persist_defaults(self):
        config = BubbleConfig(
            offset_x=self._offset.x(),
            offset_y=self._offset.y(),
            scale=self._scale,
        )
        self.apply_persisted_config(config)
        self._persist_preferences()
        self.set_text("", override_visibility=False, auto_hide=False)

    def _persist_preferences(self):
        window = self._window
        if not getattr(window, "_config", None):
            return
        window._config.setValue("ui/bubble_offset_x", float(self._offset.x()))
        window._config.setValue("ui/bubble_offset_y", float(self._offset.y()))
        window._config.setValue("ui/bubble_scale", float(self._scale))
        window._config.sync()

    # ------------------------------------------------------------------ Drag/resize handling
    def begin_transform(self, pos: QtCore.QPointF) -> bool:
        del pos
        return False

    def update_transform(self, pos: QtCore.QPointF) -> bool:
        del pos
        return False

    def end_transform(self) -> bool:
        self._dragging = False
        self._resizing = False
        self._drag_start = None
        self._resize_start = None
        self._resize_anchor = None
        return False

    def update_cursor(self, pos: QtCore.QPointF | None):
        del pos
        if self._resize_cursor_active:
            self._resize_cursor_active = False
            self._window.unsetCursor()

    # ------------------------------------------------------------------ Helpers
    def _clamp_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        return QtCore.QPointF(0.0, 0.0)

    # ------------------------------------------------------------------ Bubble text helpers
    def set_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        window = self._window
        clean = (text or "").strip()
        window._bubble_text = clean
        window._bubble_text_show_override = override_visibility and bool(clean)
        self._hide_timer.stop()
        if auto_hide and clean:
            delay = hide_delay_ms if hide_delay_ms is not None else window._bubble_auto_hide_ms
            if delay > 0:
                self._hide_timer.start(int(delay))
        window.update()

    def clear_text(self):
        window = self._window
        window._bubble_text = ""
        window._bubble_text_show_override = False
        self._hide_timer.stop()
        window.update()

    def set_visible(self, visible: bool):
        window = self._window
        window._bubble_visible = bool(visible)
        if not visible:
            window._bubble_text_show_override = False
        window._apply_state_settings()
        window.update()
