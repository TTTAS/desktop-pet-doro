"""Data models shared across the Doro application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional


class MovementRequest(NamedTuple):
    direction: tuple[float, float]
    distance_px: float
    speed_px_per_s: float
    state_key: Optional[str]
    move_state: Optional[str] = None


@dataclass
class MoveStateSettings:
    state_key: str
    direction: str = "any"
    default_distance: float | None = None
    default_speed: str | None = None
