"""DPI-aware coordinate helpers shared by AutomationManager and ports.

Qt `frameGeometry()` and `screenAt()` return logical coordinates; pynput on
Windows/X11 expects physical pixels (per-monitor DPR), while macOS CGEvent
uses logical points. Bug-class centralization: all "logical Qt point →
physical OS pixel" conversions go through :func:`compute_physical_pixel_at`.
"""

from __future__ import annotations

import sys


def compute_physical_pixel_at(
    point_logical: tuple[int, int],
    *,
    screen_origin_logical: tuple[int, int],
    device_pixel_ratio: float,
) -> tuple[int, int]:
    """Convert a Qt logical point to an OS-level physical pixel coordinate.

    Args:
        point_logical: (x, y) in Qt logical screen coords.
        screen_origin_logical: (x, y) of the containing screen's
            ``geometry().topLeft()`` — logical, but on Windows / X11 this
            origin is already DPR-aware in Qt's representation.
        device_pixel_ratio: ``QScreen.devicePixelRatio()`` for the containing
            screen.

    Returns:
        (x, y) suitable for pynput on the current platform.
    """
    if sys.platform == "darwin":
        # macOS CGEvent uses logical points; pynput passes them straight through.
        return int(point_logical[0]), int(point_logical[1])

    origin_x, origin_y = screen_origin_logical
    local_x = point_logical[0] - origin_x
    local_y = point_logical[1] - origin_y
    return (
        int(origin_x + local_x * device_pixel_ratio),
        int(origin_y + local_y * device_pixel_ratio),
    )


def compute_logical_point_from_physical(
    point_physical: tuple[int, int],
    *,
    screen_origin_logical: tuple[int, int],
    device_pixel_ratio: float,
) -> tuple[int, int]:
    """Inverse of :func:`compute_physical_pixel_at`: OS physical pixel → Qt logical point.

    The a11y element tree and mouse clicks live in physical pixels, but Qt
    window moves use logical coordinates. ``[move:to]`` needs this direction to
    place Doro at a coordinate the LLM read off the element tree.
    """
    if sys.platform == "darwin":
        return int(point_physical[0]), int(point_physical[1])

    origin_x, origin_y = screen_origin_logical
    dpr = device_pixel_ratio or 1.0
    local_x = point_physical[0] - origin_x
    local_y = point_physical[1] - origin_y
    return (
        int(origin_x + local_x / dpr),
        int(origin_y + local_y / dpr),
    )
