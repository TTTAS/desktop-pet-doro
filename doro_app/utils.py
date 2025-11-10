"""Utility helpers that do not belong to a specific domain module."""

from __future__ import annotations


def safe_float(value, default: float) -> float:
    """Convert value to float with fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Convert value to int with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
