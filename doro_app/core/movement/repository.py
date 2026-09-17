"""Movement repository — loads movements.json into data models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


# ───────────────────────────────────────────────────────────
# Data Models
# ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpeedDefaults:
    """Default speed values (px/s) keyed by tier name."""

    slow: float = 80.0
    med: float = 140.0
    fast: float = 220.0

    def resolve(self, name: str) -> float:
        """Resolve a speed tier name to px/s value.

        Supports aliases like 'medium' → 'med'.
        Falls back to ``med`` for unknown names.
        """
        aliases = {"medium": "med"}
        key = aliases.get(name.lower(), name.lower())
        value = getattr(self, key, None)
        if value is not None:
            return float(value)
        return self.med


@dataclass(frozen=True)
class MovementDefaults:
    """Top-level movement defaults parsed from movements.json."""

    speed: SpeedDefaults = field(default_factory=SpeedDefaults)
    step_px: int = 60
    completion_threshold: float = 0.5


@dataclass(frozen=True)
class MovementStateEntry:
    """A single entry from the ``movement_states`` section."""

    key: str
    state_key: str
    direction: str = "any"
    default_speed: str = "med"
    default_distance: Optional[float] = None
    animation: Optional[str] = None  # e.g. "walking.gif"

    def animation_path(self, base_dir: Path) -> Optional[Path]:
        """Resolve the animation filename to an absolute path under *base_dir*.

        Returns None when no animation is configured or the file does not exist.
        """
        if not self.animation:
            return None
        p = base_dir / self.animation
        return p if p.is_file() else None


# ───────────────────────────────────────────────────────────
# Repository
# ───────────────────────────────────────────────────────────


class MovementRepository:
    """Reads ``movements.json`` and exposes typed data models.

    The repository is **read-only** at runtime — all mutation of movement
    states still goes through the existing ``MoveStateRepository`` in the
    state package.  This class only provides the *defaults* and the
    *animation* mapping that were previously hardcoded.
    """

    def __init__(self, json_path: Path) -> None:
        self._path = json_path
        self._defaults = MovementDefaults()
        self._entries: dict[str, MovementStateEntry] = {}
        self._loaded = False

    # ── Public API ──

    @property
    def defaults(self) -> MovementDefaults:
        return self._defaults

    @property
    def entries(self) -> dict[str, MovementStateEntry]:
        return self._entries

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Parse ``movements.json`` (safe — logs warnings on failure)."""
        if not self._path.is_file():
            logger.warning("movements.json not found at %s — using built-in defaults", self._path)
            self._apply_builtin_defaults()
            return

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load movements.json: %s", exc)
            self._apply_builtin_defaults()
            return

        if not isinstance(data, dict):
            logger.warning("movements.json root is not an object — using defaults")
            self._apply_builtin_defaults()
            return

        self._parse_defaults(data.get("defaults", {}))
        self._parse_entries(data.get("movement_states", {}))
        self._loaded = True
        logger.info(
            "Loaded movements.json: %d entries, step_px=%d",
            len(self._entries),
            self._defaults.step_px,
        )

    def get_entry(self, key: str) -> Optional[MovementStateEntry]:
        return self._entries.get(key)

    def resolve_speed(self, name: str) -> float:
        """Shortcut to resolve a speed tier via the loaded defaults."""
        return self._defaults.speed.resolve(name)

    def resolve_animation_path(self, key: str) -> Optional[Path]:
        """Resolve the animation file for a movement state key."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry.animation_path(self._path.parent)

    # ── Internals ──

    def _apply_builtin_defaults(self) -> None:
        """Ensure we always have sensible fallback values."""
        self._defaults = MovementDefaults()
        self._entries = {
            "walking": MovementStateEntry(
                key="walking",
                state_key="walking",
                direction="any",
                default_speed="med",
                animation="walking.gif",
            ),
        }
        self._loaded = True

    def _parse_defaults(self, raw: object) -> None:
        if not isinstance(raw, dict):
            self._defaults = MovementDefaults()
            return

        speed_raw = raw.get("speed", {})
        if isinstance(speed_raw, dict):
            speed = SpeedDefaults(
                slow=float(speed_raw.get("slow", 80.0)),
                med=float(speed_raw.get("med", 140.0)),
                fast=float(speed_raw.get("fast", 220.0)),
            )
        else:
            speed = SpeedDefaults()

        self._defaults = MovementDefaults(
            speed=speed,
            step_px=int(raw.get("step_px", 60)),
            completion_threshold=float(raw.get("completion_threshold", 0.5)),
        )

    def _parse_entries(self, raw: object) -> None:
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                entry = MovementStateEntry(
                    key=key,
                    state_key=value.get("state_key", key),
                    direction=value.get("direction", "any"),
                    default_speed=value.get("default_speed", "med"),
                    default_distance=value.get("default_distance"),
                    animation=value.get("animation"),
                )
                self._entries[key] = entry
            except (ValueError, TypeError):
                logger.warning("Skipping invalid movement_states entry: %s", key)
