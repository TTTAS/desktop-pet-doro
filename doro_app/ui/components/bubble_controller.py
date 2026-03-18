"""Bubble (speech panel) controller for the Doro window."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from ...constants import BUBBLE_SCALE_MIN, BUBBLE_SCALE_MAX
from ...utils.config_manager import ConfigManager


@dataclass
class BubbleConfig:
    offset_x: float = 120.0
    offset_y: float = -110.0
    scale: float = 1.0
    auto_hide_ms: int = 6000


class BubbleController(QtCore.QObject):
    """
    Manages bubble (speech panel) display, positioning, and auto-hide behavior.

    Uses Signal/Slot pattern to decouple from Window implementation.

    Signals:
        text_changed: Emitted when bubble text changes (str: text, bool: override_visibility)
        visibility_changed: Emitted when bubble visibility changes (bool: visible)
        offset_changed: Emitted when bubble offset changes (QPointF: offset)
        scale_changed: Emitted when bubble scale changes (float: scale)
        repaint_requested: Emitted when window needs repaint
        update_bubble_side_requested: Emitted when bubble side needs update based on offset
    """

    # Signals for decoupling from Window
    text_changed = QtCore.Signal(str, bool)  # text, override_visibility
    visibility_changed = QtCore.Signal(bool)  # visible
    offset_changed = QtCore.Signal(QtCore.QPointF)  # offset
    scale_changed = QtCore.Signal(float)  # scale
    repaint_requested = QtCore.Signal()  # request window update
    update_bubble_side_requested = QtCore.Signal()  # request bubble side update
    state_settings_apply_requested = QtCore.Signal(str)  # request state settings apply with state_key

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self._config_manager = config_manager
        self._offset = QtCore.QPointF(0.0, 0.0)
        self._scale = 1.0
        self._text = ""
        self._text_show_override = False
        self._visible = True

        # Auto-hide timer (owned by BubbleController, not Window)
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timer_timeout)

        # Auto-hide default delay (can be overridden per-message)
        self._default_auto_hide_ms = 6000

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

    # ------------------------------------------------------------------ Offset/scale manipulation
    def apply_offset(self, candidate: QtCore.QPointF, *, persist: bool = False):
        self._offset = QtCore.QPointF(candidate)
        self.offset_changed.emit(QtCore.QPointF(self._offset))
        self.update_bubble_side_requested.emit()
        if persist:
            self.persist_preferences()
        self.repaint_requested.emit()

    def set_scale(self, value: float, *, persist: bool = False):
        self._scale = max(BUBBLE_SCALE_MIN, min(BUBBLE_SCALE_MAX, float(value)))
        self.scale_changed.emit(self._scale)
        if persist:
            self.persist_preferences()
        self.repaint_requested.emit()

    def persist_defaults(self):
        config = BubbleConfig(
            offset_x=self._offset.x(),
            offset_y=self._offset.y(),
            scale=self._scale,
        )
        self.apply_persisted_config(config)
        self.persist_preferences()
        self.set_text("", override_visibility=False, auto_hide=False)

    def persist_preferences(self):
        """Persist bubble preferences to configuration."""
        self._config_manager.update_ui(
            bubble_offset_x=float(self._offset.x()),
            bubble_offset_y=float(self._offset.y()),
            bubble_scale=float(self._scale),
        )
        self._config_manager.save()

    # ------------------------------------------------------------------ Bubble text helpers
    def set_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        """
        Set bubble text and optionally schedule auto-hide.

        Args:
            text: Text to display (empty string clears the bubble)
            override_visibility: Show bubble even if visibility is disabled
            auto_hide: If True and delay > 0, automatically hide after delay
            hide_delay_ms: Custom delay in milliseconds (None = use default)

        Fixed: Previously, auto_hide=False would prevent timer from working.
        Now: If auto_hide=False, message stays forever (until manually cleared).
                If auto_hide=True with delay=0, also stays forever.
                Otherwise, hides after delay.
        """
        clean = (text or "").strip()

        # Update internal state
        self._text = clean
        self._text_show_override = override_visibility and bool(clean)

        # Emit signal to notify observers
        self.text_changed.emit(clean, self._text_show_override)

        # Stop any existing timer
        self._hide_timer.stop()

        # Schedule auto-hide if requested
        if clean:  # Only schedule if there's actually text
            if auto_hide:
                delay = hide_delay_ms if hide_delay_ms is not None else self._default_auto_hide_ms
                if delay > 0:
                    self._hide_timer.start(int(delay))
            # else: auto_hide=False means keep message visible indefinitely

        # Request repaint
        self.repaint_requested.emit()

    def _on_hide_timer_timeout(self):
        """Called when auto-hide timer expires."""
        self.clear_text()

    def clear_text(self):
        """Clear bubble text immediately."""
        self._text = ""
        self._text_show_override = False
        self._hide_timer.stop()
        self.text_changed.emit("", False)
        self.repaint_requested.emit()

    def set_visible(self, visible: bool, current_state_key: str | None = None):
        """
        Set bubble visibility.

        Args:
            visible: Whether bubble should be visible
            current_state_key: Current state key for applying settings (optional)
        """
        self._visible = bool(visible)
        if not visible:
            self._text_show_override = False
        self.visibility_changed.emit(self._visible)
        if current_state_key:
            self.state_settings_apply_requested.emit(current_state_key)
        self.repaint_requested.emit()
