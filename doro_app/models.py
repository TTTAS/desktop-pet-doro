"""Data models shared across the Doro application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Optional


class MovementRequest(NamedTuple):
    direction: tuple[float, float]
    distance_px: float
    speed_px_per_s: float
    state_key: Optional[str]
    move_state: Optional[str] = None


@dataclass
class StateSettings:
    label: str
    bob_amplitude: float = 6.0
    scale_amplitude: float = 0.04
    gradient_top: str = "#FFFFFFFF"
    gradient_mid: str = "#FF9BE3FF"
    gradient_bottom: str = "#FF6CC1F0"
    cheeks_alpha: float = 204
    blush_color: str = "#FFC0C0"
    eye_color: str = "#222222"
    bubble_visible: bool = True
    bubble_alpha: float = 170
    name_tag: str = "doro"
    gif_path: str | None = None
    gif_variants: list[str] = field(default_factory=list)


@dataclass
class MoveStateSettings:
    state_key: str
    direction: str = "any"
    default_distance: float | None = None
    default_speed: str | None = None
