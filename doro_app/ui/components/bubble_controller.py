"""Bubble (speech panel) controller for the Doro window."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from ...constants import (
    BUBBLE_SCALE_MIN,
    BUBBLE_SCALE_MAX,
    BUBBLE_CHUNK_MAX_CHARS,
    BUBBLE_CHUNK_MIN_READ_MS,
    BUBBLE_CHUNK_MAX_READ_MS,
    BUBBLE_CHUNK_PER_CHAR_MS,
)
from ...utils.config_manager import ConfigManager

# Sentence-ending punctuation used to split long text at natural boundaries
# (CJK 。！？…、newlines, plus ASCII . ! ?). A unit keeps its trailing marks.
_SENTENCE_SPLIT_RE = re.compile(r"[^。！？!?…\n]*[。！？!?…\n]+|[^。！？!?…\n]+")
_SENTENCE_ENDERS = "。！？!?…\n"


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
        # Doubles as the "advance to next chunk" timer while a multi-part
        # message is being spoken (see set_text / _on_hide_timer_timeout).
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timer_timeout)

        # Auto-hide default delay (can be overridden per-message)
        self._default_auto_hide_ms = 6000

        # Multi-part ("speak in chunks") sequence state. When a long reply is
        # split, the remaining pieces wait here and the display settings that
        # applied to the whole message are remembered for the final piece.
        self._chunk_queue: list[str] = []
        self._seq_override_visibility = True
        self._seq_auto_hide = True
        self._seq_hide_delay_ms: int | None = None

    # ------------------------------------------------------------------ State access
    @property
    def text(self) -> str:
        return self._text

    @property
    def text_show_override(self) -> bool:
        return self._text_show_override

    @property
    def offset(self) -> QtCore.QPointF:
        return QtCore.QPointF(self._offset)

    @property
    def scale(self) -> float:
        return float(self._scale)

    @property
    def visible(self) -> bool:
        return self._visible

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

        Long messages are split into several short bubbles shown one after
        another ("Doro speaks in parts") so a single bubble never grows tall
        enough to push the sprite up or run off the bottom of the screen. Each
        mid-sequence piece stays up for a reading-time delay; the final piece
        follows the normal auto-hide rules below.

        Fixed: Previously, auto_hide=False would prevent timer from working.
        Now: If auto_hide=False, message stays forever (until manually cleared).
                If auto_hide=True with delay=0, also stays forever.
                Otherwise, hides after delay.
        """
        clean = (text or "").strip()

        # Any new message cancels a chunk sequence still in progress.
        self._hide_timer.stop()
        self._chunk_queue = []

        # Empty text just clears the bubble.
        if not clean:
            self._text = ""
            self._text_show_override = False
            self.text_changed.emit("", False)
            self.repaint_requested.emit()
            return

        # Remember how the whole message wanted to be shown/hidden so the last
        # chunk can honour it.
        self._seq_override_visibility = override_visibility
        self._seq_auto_hide = auto_hide
        self._seq_hide_delay_ms = hide_delay_ms

        # Split into chunks; the first shows now, the rest queue up.
        chunks = self._split_into_chunks(clean)
        self._chunk_queue = chunks
        self._show_next_chunk()

    def _show_next_chunk(self):
        """Display the next queued chunk and schedule what follows it.

        Mid-sequence chunks advance after a reading-time delay; the final chunk
        falls back to the message's original auto-hide behaviour.
        """
        if not self._chunk_queue:
            return

        chunk = self._chunk_queue.pop(0)

        self._text = chunk
        self._text_show_override = self._seq_override_visibility and bool(chunk)
        self.text_changed.emit(chunk, self._text_show_override)

        if self._chunk_queue:
            # More to say — keep this piece up just long enough to read it.
            self._hide_timer.start(self._reading_delay_ms(chunk))
        elif self._seq_auto_hide:
            delay = (
                self._seq_hide_delay_ms
                if self._seq_hide_delay_ms is not None
                else self._default_auto_hide_ms
            )
            if delay > 0:
                self._hide_timer.start(int(delay))
        # else: last chunk with auto_hide off — stays until cleared.

        self.repaint_requested.emit()

    @staticmethod
    def _reading_delay_ms(chunk: str) -> int:
        """How long a mid-sequence chunk stays up, scaled to its length."""
        estimate = BUBBLE_CHUNK_MIN_READ_MS + len(chunk) * BUBBLE_CHUNK_PER_CHAR_MS
        return int(min(BUBBLE_CHUNK_MAX_READ_MS, max(BUBBLE_CHUNK_MIN_READ_MS, estimate)))

    @staticmethod
    def _split_into_chunks(text: str) -> list[str]:
        """Break *text* into bubble-sized pieces at sentence boundaries.

        Short messages pass through untouched (a single-item list). Longer ones
        are packed greedily up to ``BUBBLE_CHUNK_MAX_CHARS``; any single
        sentence longer than that is hard-wrapped so no piece ever exceeds the
        limit.
        """
        text = text.strip()
        if len(text) <= BUBBLE_CHUNK_MAX_CHARS:
            return [text]

        # Sentence-ish units, then hard-wrap any unit that is itself too long.
        units: list[str] = []
        for match in _SENTENCE_SPLIT_RE.findall(text):
            unit = match.strip()
            if not unit:
                continue
            if len(unit) <= BUBBLE_CHUNK_MAX_CHARS:
                units.append(unit)
            else:
                for i in range(0, len(unit), BUBBLE_CHUNK_MAX_CHARS):
                    units.append(unit[i:i + BUBBLE_CHUNK_MAX_CHARS])

        # Greedily pack units into chunks.
        chunks: list[str] = []
        current = ""
        for unit in units:
            if not current:
                current = unit
            elif len(current) + len(unit) <= BUBBLE_CHUNK_MAX_CHARS:
                current += unit
            else:
                chunks.append(current)
                current = unit
        if current:
            chunks.append(current)

        return chunks or [text]

    def _on_hide_timer_timeout(self):
        """Timer fired: advance to the next chunk, or hide if none remain."""
        if self._chunk_queue:
            self._show_next_chunk()
        else:
            self.clear_text()

    def clear_text(self):
        """Clear bubble text immediately."""
        self._text = ""
        self._text_show_override = False
        self._hide_timer.stop()
        self._chunk_queue = []
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
