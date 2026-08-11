"""Pre-written companion lines, picked by situation and mood.

These are shown directly in Doro's bubble **without** an LLM call — the
cheap, always-available way for her to have a life. Idle chatter and the
event-driven reactions (long-sitting, late-night, morning, app-switch) all
draw from here; the LLM is reserved for real conversation and the rare
"comment on my screen" moment.

Pure logic apart from the one-time JSON load, so it's easy to test.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ...utils.logger import get_logger
from .models import MoodState

logger = get_logger(__name__)


class CompanionLines:
    """A bag of Doro-voice lines grouped by key, with mood-aware idle pick."""

    def __init__(self, path: Path):
        self._by_key: dict[str, list[str]] = self._load(Path(path))

    # ── loading ──────────────────────────────────────────────────────────

    def _load(self, path: Path) -> dict[str, list[str]]:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("companion_lines.json not found at %s", path)
            return {}
        except OSError as exc:
            logger.warning("Failed to read companion lines: %s", exc)
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("companion_lines.json is not valid JSON: %s", exc)
            return {}
        if not isinstance(data, dict):
            return {}
        # Keep only list-of-nonempty-strings buckets; skip "_comment" etc.
        result: dict[str, list[str]] = {}
        for key, value in data.items():
            if key.startswith("_") or not isinstance(value, list):
                continue
            lines = [str(item).strip() for item in value if str(item).strip()]
            if lines:
                result[key] = lines
        return result

    # ── picking ──────────────────────────────────────────────────────────

    def pick(self, *keys: str) -> str | None:
        """Random line from the first key that has any lines; else None."""
        for key in keys:
            lines = self._by_key.get(key)
            if lines:
                return random.choice(lines)
        return None

    def pick_idle(self, mood: MoodState | None) -> str | None:
        """Choose an idle line whose tone matches the current mood.

        Affection gates first — a Doro who feels ignored is lonely
        regardless of momentary mood — then mood picks the band. Always
        falls back through neutral so a sparse file still says *something*.
        """
        if mood is None:
            return self.pick("idle_neutral", "lonely")

        if mood.affection < 0.15:
            primary = "lonely"
        elif mood.mood >= 0.15:
            primary = "idle_happy"
        elif mood.mood <= -0.15:
            primary = "idle_low"
        else:
            primary = "idle_neutral"

        return self.pick(primary, "idle_neutral", "lonely")

    def has(self, key: str) -> bool:
        return bool(self._by_key.get(key))
