"""Parsing and formatting helpers for movement commands."""

from __future__ import annotations

import math
from typing import Optional

from PySide6 import QtCore

from ...utils.actions import MOVE_DIRECTIONS


def normalize_direction_key(value: str) -> str:
    key = (value or "").strip()
    if not key:
        return ""
    key = key.replace(" ", "").replace("_", "").replace("-", "")
    return key.lower() if key.isascii() else key


def parse_move_bracket(token: str) -> tuple[str, dict[str, str]] | None:
    parts = [part.strip() for part in token.split(";") if part.strip()]
    if not parts:
        return None
    header = parts[0]
    prefix = header
    action_part = ""
    if ":" in header:
        prefix, action_part = header.split(":", 1)
    if prefix.strip().lower() != "move":
        return None
    action_key = ""
    params: dict[str, str] = {}
    param_candidates: list[str] = []

    action_part = action_part.strip()
    if action_part:
        if "=" in action_part:
            param_candidates.append(action_part)
        else:
            action_key = action_part

    for part in parts[1:]:
        if "=" not in part:
            continue
        param_candidates.append(part)

    for part in param_candidates:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        params[key.strip().lower()] = value.strip()

    return action_key, params


def direction_vector_from_string(value: str) -> tuple[int, int] | None:
    key = normalize_direction_key(value)
    vec = MOVE_DIRECTIONS.get(key)
    if vec:
        return vec
    if ";" in value:
        dx = None
        dy = None
        try:
            for part in value.split(";"):
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                if k.strip().lower() == "dx":
                    dx = float(v.strip())
                elif k.strip().lower() == "dy":
                    dy = float(v.strip())
        except ValueError:
            return None
        if dx is not None and dy is not None:
            length = math.hypot(dx, dy)
            if length > 0:
                return (dx / length, dy / length)
    return None


def direction_key(direction: tuple[float, float]) -> tuple[int, int]:
    dx, dy = direction
    return (
        int(math.copysign(1, dx)) if abs(dx) > 0.2 else 0,
        int(math.copysign(1, dy)) if abs(dy) > 0.2 else 0,
    )


def direction_label(direction: tuple[float, float]) -> str:
    key = direction_key(direction)
    mapping = {
        (-1, 0): "左",
        (1, 0): "右",
        (0, -1): "上",
        (0, 1): "下",
        (-1, -1): "左上",
        (1, -1): "右上",
        (-1, 1): "左下",
        (1, 1): "右下",
    }
    return mapping.get(key, "未知方向")


def format_move_report(
    pos: QtCore.QPoint, direction_label_text: Optional[str], dx: int, dy: int
) -> str:
    prefix = f"往{direction_label_text}" if direction_label_text else "移動"
    deltas = []
    if dx:
        deltas.append(f"dx={dx}")
    if dy:
        deltas.append(f"dy={dy}")
    delta_info = f" ({', '.join(deltas)})" if deltas else ""
    return f"{prefix}，位置 {pos.x()}, {pos.y()}{delta_info}"
