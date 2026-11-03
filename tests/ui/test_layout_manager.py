"""Tests for WindowLayoutManager - pure layout calculation logic."""

from unittest.mock import Mock, patch

import pytest
from PySide6 import QtCore, QtGui

from doro_app.ui.layout.layout_manager import WindowLayoutManager


@pytest.fixture
def mock_font_metrics():
    """Mock QFontMetrics to avoid Qt GUI dependency in headless environments."""
    mock_metrics = Mock(spec=QtGui.QFontMetrics)

    # Mock lineSpacing() for empty text
    mock_metrics.lineSpacing.return_value = 16

    # Mock boundingRect() for text measurement
    def mock_bounding_rect(*args, **kwargs):
        mock_rect = Mock(spec=QtCore.QRect)
        # Estimate height based on text content if provided
        if len(args) >= 3:  # Has text argument
            text = args[2]
            # Rough estimate: ~16px per line
            lines = max(1, len(text) // 30 + text.count("\n"))
            mock_rect.height.return_value = lines * 16
        else:
            mock_rect.height.return_value = 16
        return mock_rect

    mock_metrics.boundingRect.side_effect = mock_bounding_rect

    with patch("PySide6.QtGui.QFontMetrics", return_value=mock_metrics):
        yield mock_metrics


class TestGetAvailableScreenGeometry:
    """Test screen geometry retrieval."""

    def test_returns_rect_when_no_window_provided(self):
        """Test getting screen geometry without a window."""
        rect = WindowLayoutManager.get_available_screen_geometry(None)

        assert isinstance(rect, QtCore.QRect)
        # Should return either actual screen or fallback
        assert rect.width() > 0
        assert rect.height() > 0

    def test_fallback_dimensions_are_reasonable(self):
        """Test fallback dimensions when no screen available."""
        # This test documents the fallback behavior
        # In actual usage, QApplication.primaryScreen() usually exists
        rect = WindowLayoutManager.get_available_screen_geometry(None)

        # Minimum reasonable screen size
        assert rect.width() >= 800
        assert rect.height() >= 600


class TestClampPosition:
    """Test window position clamping."""

    def test_position_within_bounds_unchanged(self):
        """Test that positions already within bounds are not changed."""
        desired = QtCore.QPoint(100, 100)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped == desired

    def test_position_too_far_left_is_clamped(self):
        """Test clamping when window would go off left edge."""
        desired = QtCore.QPoint(-100, 100)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped.x() == 0  # Clamped to left edge
        assert clamped.y() == 100  # Y unchanged

    def test_position_too_far_right_is_clamped(self):
        """Test clamping when window would go off right edge."""
        desired = QtCore.QPoint(2000, 100)  # Way off screen
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        # Should be clamped to right edge (1920 - 200 = 1720)
        assert clamped.x() == 1720
        assert clamped.y() == 100

    def test_position_too_far_top_is_clamped(self):
        """Test clamping when window would go off top edge."""
        desired = QtCore.QPoint(100, -50)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped.x() == 100
        assert clamped.y() == 0  # Clamped to top edge

    def test_position_too_far_bottom_is_clamped(self):
        """Test clamping when window would go off bottom edge."""
        desired = QtCore.QPoint(100, 2000)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped.x() == 100
        # Should be clamped to bottom edge (1080 - 200 = 880)
        assert clamped.y() == 880

    def test_both_x_and_y_clamped_simultaneously(self):
        """Test clamping when both X and Y are out of bounds."""
        desired = QtCore.QPoint(-100, 2000)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped.x() == 0  # Left edge
        assert clamped.y() == 880  # Bottom edge

    def test_window_larger_than_screen(self):
        """Test behavior when window is larger than screen."""
        desired = QtCore.QPoint(100, 100)
        window_size = QtCore.QSize(3000, 2000)  # Huge window
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        # Should clamp to top-left (can't fit window on screen anyway)
        assert clamped.x() == 0
        assert clamped.y() == 0

    def test_screen_with_offset(self):
        """Test clamping with screen that doesn't start at (0,0)."""
        # Simulates secondary monitor to the right
        desired = QtCore.QPoint(2000, 100)
        window_size = QtCore.QSize(200, 200)
        screen_rect = QtCore.QRect(1920, 0, 1920, 1080)  # Second monitor

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        # Should stay within the second monitor's bounds
        assert clamped.x() >= 1920  # At least at left edge of second monitor
        assert clamped.x() <= (1920 + 1920 - 200)  # At most at right edge

    def test_tiny_window(self):
        """Test clamping with very small window."""
        desired = QtCore.QPoint(100, 100)
        window_size = QtCore.QSize(10, 10)
        screen_rect = QtCore.QRect(0, 0, 1920, 1080)

        clamped = WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

        assert clamped == desired  # Tiny window easily fits


class TestComputePreferredWindowSize:
    """Doro's window is the sprite itself; the bubble has its own window."""

    def test_window_matches_the_sprite(self):
        assert WindowLayoutManager.compute_preferred_window_size(QtCore.QSize(200, 270)) == (
            200,
            270,
        )

    def test_tiny_sprites_keep_a_usable_minimum(self):
        assert WindowLayoutManager.compute_preferred_window_size(QtCore.QSize(40, 60)) == (
            120,
            120,
        )
