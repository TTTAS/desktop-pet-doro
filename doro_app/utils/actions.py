"""Utility helpers for parsing action and movement instructions."""

from __future__ import annotations

import re

ACTION_ALIASES: dict[str, str] = {
    "idle": "idle",
    "default": "idle",
    "sleep": "idle",
    "sleepy": "idle",
    "nap": "idle",
    "rest": "idle",
    "relax": "idle",
    "chill": "idle",
    "calm": "idle",
    "excited": "idle",
    "happy": "idle",
    "dance": "idle",
    "wave": "idle",
    "party": "idle",
}

MOVE_TOKEN_PATTERN = re.compile(
    r"^(?:move|mv|walk|go|travel|shift|step|run|向|往|移動|走|行)[\s:_-]*([a-z]+|[上下左右]{1,2})$",
    re.IGNORECASE,
)

MOVE_DIRECTIONS: dict[str, tuple[int, int]] = {
    "left": (-1, 0),
    "l": (-1, 0),
    "west": (-1, 0),
    "right": (1, 0),
    "r": (1, 0),
    "east": (1, 0),
    "up": (0, -1),
    "u": (0, -1),
    "north": (0, -1),
    "down": (0, 1),
    "d": (0, 1),
    "south": (0, 1),
    "upleft": (-1, -1),
    "leftup": (-1, -1),
    "ul": (-1, -1),
    "up-left": (-1, -1),
    "left-up": (-1, -1),
    "upright": (1, -1),
    "rightup": (1, -1),
    "ur": (1, -1),
    "up-right": (1, -1),
    "right-up": (1, -1),
    "downleft": (-1, 1),
    "leftdown": (-1, 1),
    "dl": (-1, 1),
    "down-left": (-1, 1),
    "left-down": (-1, 1),
    "downright": (1, 1),
    "rightdown": (1, 1),
    "dr": (1, 1),
    "down-right": (1, 1),
    "right-down": (1, 1),
    "上": (0, -1),
    "下": (0, 1),
    "左": (-1, 0),
    "右": (1, 0),
    "上左": (-1, -1),
    "上右": (1, -1),
    "下左": (-1, 1),
    "下右": (1, 1),
    "左上": (-1, -1),
    "右上": (1, -1),
    "左下": (-1, 1),
    "右下": (1, 1),
}
