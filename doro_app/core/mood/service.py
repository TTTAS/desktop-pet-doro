"""Runtime owner of Doro's mood state: load, record events, persist.

Thin Qt wrapper around the pure :class:`MoodState`. Persists to a small
JSON file next to the app log (``~/.doro/mood.json``) so the bond survives
restarts. Saves are debounced — a flurry of drag "play" events collapses
into one write — and flushed on quit.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore

from ...utils.logger import get_logger
from .models import MoodEvent, MoodState

logger = get_logger(__name__)

# Drag/click bursts can fire many events per second; collapse them.
_SAVE_DEBOUNCE_MS = 400


class MoodService(QtCore.QObject):
    """Owns the live :class:`MoodState` and its persistence."""

    def __init__(self, storage_path: Path, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._path = Path(storage_path)
        self._state = self._load()

        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.save)

    # ── public API ───────────────────────────────────────────────────────

    def record_event(self, event: MoodEvent) -> None:
        """Apply an interaction's nudge and schedule a persist."""
        self._state.apply_event(event)
        logger.debug(
            "mood event %s -> mood=%.2f affection=%.2f",
            MoodEvent(event).value,
            self._state.mood,
            self._state.affection,
        )
        self._save_timer.start()

    def describe(self) -> str:
        """Prompt-ready mood block, decayed to the present moment."""
        return self._state.describe()

    @property
    def state(self) -> MoodState:
        return self._state

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._state.to_dict()), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Failed to save mood state: %s", exc)

    # ── internals ────────────────────────────────────────────────────────

    def _load(self) -> MoodState:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return MoodState()
        except OSError as exc:
            logger.warning("Failed to read mood state: %s", exc)
            return MoodState()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("mood.json is not valid JSON: %s", exc)
            return MoodState()
        return MoodState.from_dict(data)
