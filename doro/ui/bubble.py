from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets


class BubbleController(QtCore.QObject):
    """
    Encapsulates state and helpers for the speech bubble so the main window can
    focus on high-level interaction logic.
    """

    def __init__(self, owner: QtWidgets.QWidget, *, auto_hide_ms: int = 6000):
        super().__init__(owner)
        self._owner = owner
        self._config: Optional[QtCore.QSettings] = None
        self.visible = True
        self.alpha = 170.0
        self.side = "center"
        self.text = ""
        self.text_show_override = False
        self.auto_hide_ms = auto_hide_ms
        self.offset = QtCore.QPointF(0.0, 0.0)
        self.scale = 1.0
        self.dragging = False
        self.resizing = False
        self.drag_start: QtCore.QPointF | None = None
        self.initial_offset = QtCore.QPointF(0.0, 0.0)
        self.resize_start: QtCore.QPointF | None = None
        self.resize_anchor: QtCore.QPointF | None = None
        self.initial_scale = 1.0
        self.resize_cursor_active = False
        self.panel_rect: QtCore.QRectF | None = None
        self.initial_panel_size = QtCore.QSizeF(0.0, 0.0)
        self.width_hint = 360.0
        self.height_hint = 110.0

        self.hide_timer = QtCore.QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.clear_text)

    # ------------------------------------------------------------------ #
    # Config binding
    # ------------------------------------------------------------------ #
    def attach_config(self, config: QtCore.QSettings):
        self._config = config

    def persist_preferences(self):
        if not self._config:
            return
        self._config.setValue("ui/bubble_offset_x", float(self.offset.x()))
        self._config.setValue("ui/bubble_offset_y", float(self.offset.y()))
        self._config.setValue("ui/bubble_scale", float(self.scale))
        self._config.sync()

    # ------------------------------------------------------------------ #
    # State helpers
    # ------------------------------------------------------------------ #
    def set_scale(self, value: float, *, persist: bool = False):
        try:
            scaled = float(value)
        except (TypeError, ValueError):
            scaled = 1.0
        scaled = max(0.4, min(2.5, scaled))
        self.scale = scaled
        if persist:
            self.persist_preferences()
        self._owner.update()

    def show_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        clean = (text or "").strip()
        self.text = clean
        self.text_show_override = override_visibility and bool(clean)
        self.hide_timer.stop()
        if auto_hide and clean:
            delay = hide_delay_ms if hide_delay_ms is not None else self.auto_hide_ms
            if delay and delay > 0:
                self.hide_timer.start(int(delay))
        self._owner.update()
        apply_size = getattr(self._owner, "_apply_window_preferred_size", None)
        if callable(apply_size):
            apply_size()

    def clear_text(self):
        self.text = ""
        self.text_show_override = False
        self.hide_timer.stop()
        self._owner.update()
        apply_size = getattr(self._owner, "_apply_window_preferred_size", None)
        if callable(apply_size):
            apply_size()

    def update_side_from_offset(self):
        self.side = "center"

    # ------------------------------------------------------------------ #
    # Interaction helpers
    # ------------------------------------------------------------------ #
    def _has_panel(self) -> bool:
        rect = self.panel_rect
        return rect is not None and rect.width() > 0 and rect.height() > 0

    def begin_transform(
        self,
        owner: QtWidgets.QWidget,
        pos: QtCore.QPointF,
        handle_rect: QtCore.QRectF | None,
    ) -> bool:
        if not self._has_panel():
            return False

        rect = self.panel_rect
        if handle_rect and handle_rect.contains(pos):
            self.resizing = True
            self.resize_start = QtCore.QPointF(pos)
            self.resize_anchor = QtCore.QPointF(rect.topLeft())
            self.initial_scale = float(self.scale)
            self.initial_panel_size = QtCore.QSizeF(rect.width(), rect.height())
            owner.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
            self.resize_cursor_active = True
            return True

        if rect.contains(pos):
            self.dragging = True
            self.drag_start = QtCore.QPointF(pos)
            self.initial_offset = QtCore.QPointF(self.offset)
            owner.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            return True

        return False

    def update_transform(self, owner: QtWidgets.QWidget, pos: QtCore.QPointF) -> bool:
        changed = False
        layout_change = False
        if self.dragging and self.drag_start is not None:
            delta = pos - self.drag_start
            candidate = QtCore.QPointF(self.initial_offset + delta)
            apply_offset = getattr(owner, "_apply_bubble_offset", None)
            if callable(apply_offset):
                apply_offset(candidate, persist=False)
            else:
                clamp = getattr(owner, "_clamp_bubble_offset", None)
                if callable(clamp):
                    candidate = clamp(candidate)
                self.offset = candidate
            changed = True

        elif self.resizing and self.resize_start is not None:
            delta = pos - self.resize_start
            base_width = max(80.0, float(self.initial_panel_size.width() or 0.0))
            base_height = max(60.0, float(self.initial_panel_size.height() or 0.0))
            new_width = max(60.0, base_width + delta.x())
            new_height = max(40.0, base_height + delta.y())
            scale_x = new_width / base_width if base_width else 1.0
            scale_y = new_height / base_height if base_height else 1.0
            scale_factor = max(scale_x, scale_y)
            new_scale = max(0.4, min(2.5, float(self.initial_scale) * scale_factor))
            if abs(new_scale - self.scale) > 1e-3:
                self.scale = new_scale
                changed = True
                layout_change = True

        if changed:
            if layout_change:
                apply_size = getattr(owner, "_apply_window_preferred_size", None)
                if callable(apply_size):
                    apply_size()
                else:
                    owner.update()
            else:
                owner.update()
            return True
        return self.dragging or self.resizing

    def update_cursor(
        self,
        owner: QtWidgets.QWidget,
        pos: QtCore.QPointF | None,
        handle_rect: QtCore.QRectF | None,
    ):
        if self.dragging:
            owner.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            return
        if self.resizing:
            owner.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
            return

        if pos is None:
            self.resize_cursor_active = False
            owner.unsetCursor()
            return

        if handle_rect and handle_rect.contains(pos):
            owner.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
            self.resize_cursor_active = True
            return

        rect = self.panel_rect
        if rect and rect.contains(pos):
            owner.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            self.resize_cursor_active = False
        else:
            self.resize_cursor_active = False
            owner.unsetCursor()

    def end_transform(self, owner: QtWidgets.QWidget) -> bool:
        was_transforming = self.dragging or self.resizing
        if not was_transforming:
            return False
        self.dragging = False
        self.resizing = False
        self.drag_start = None
        self.resize_start = None
        self.resize_anchor = None
        self.initial_panel_size = QtCore.QSizeF(0.0, 0.0)
        owner.unsetCursor()
        self.persist_preferences()
        return True


__all__ = ["BubbleController"]
