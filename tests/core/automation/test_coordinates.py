"""Tests for the logical<->physical pixel conversions used by [move:to]."""

from __future__ import annotations

import sys

import pytest

from doro_app.core.automation.coordinates import (
    compute_logical_point_from_physical,
    compute_physical_pixel_at,
)

_skip_darwin = pytest.mark.skipif(
    sys.platform == "darwin", reason="macOS passes points through unchanged"
)


@_skip_darwin
def test_inverse_of_physical_at_dpr_1_5():
    origin = (0, 0)
    logical = (120, 80)
    physical = compute_physical_pixel_at(
        logical, screen_origin_logical=origin, device_pixel_ratio=1.5
    )
    back = compute_logical_point_from_physical(
        physical, screen_origin_logical=origin, device_pixel_ratio=1.5
    )
    assert back == logical


@_skip_darwin
def test_dpr_1_is_identity():
    assert compute_logical_point_from_physical(
        (200, 100), screen_origin_logical=(0, 0), device_pixel_ratio=1.0
    ) == (200, 100)


@_skip_darwin
def test_respects_non_zero_screen_origin():
    # Physical pixel sitting 300px into a screen whose origin is logical (1000,0)
    # at DPR 2.0 maps back to 150 logical px past the origin.
    assert compute_logical_point_from_physical(
        (1300, 200), screen_origin_logical=(1000, 0), device_pixel_ratio=2.0
    ) == (1150, 100)
