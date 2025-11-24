"""Tests for WindowLayoutManager - pure layout calculation logic."""

import pytest
from PySide6 import QtCore, QtGui

from doro_app.ui.layout_manager import WindowLayoutManager


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


class TestComputePanelSizeHint:
    """Test panel size calculation."""

    def test_empty_text_returns_minimum_height(self):
        """Test panel size with no text."""
        sprite_size = QtCore.QSize(200, 200)
        bubble_text = ""

        width, height = WindowLayoutManager.compute_panel_size_hint(sprite_size, bubble_text)

        # Width should be based on sprite
        assert width >= 160.0
        assert width >= 200.0  # At least sprite width

        # Height should be minimum with just one line spacing
        assert height >= 80.0
        assert height < 150.0  # Not too tall for empty text

    def test_short_text_increases_height(self):
        """Test panel size with short text."""
        sprite_size = QtCore.QSize(200, 200)
        short_text = "Hello"

        width, height = WindowLayoutManager.compute_panel_size_hint(sprite_size, short_text)

        assert width >= 160.0
        assert height >= 80.0

    def test_long_text_increases_height_more(self):
        """Test that longer text creates taller panels."""
        sprite_size = QtCore.QSize(200, 200)
        short_text = "Hi"
        long_text = "This is a much longer text that will wrap across multiple lines and require more vertical space to display properly in the bubble."

        _, short_height = WindowLayoutManager.compute_panel_size_hint(sprite_size, short_text)
        _, long_height = WindowLayoutManager.compute_panel_size_hint(sprite_size, long_text)

        # Long text should create taller panel
        assert long_height > short_height

    def test_wider_sprite_creates_wider_panel(self):
        """Test that sprite width affects panel width."""
        small_sprite = QtCore.QSize(100, 100)
        large_sprite = QtCore.QSize(400, 400)
        text = "Same text"

        small_width, _ = WindowLayoutManager.compute_panel_size_hint(small_sprite, text)
        large_width, _ = WindowLayoutManager.compute_panel_size_hint(large_sprite, text)

        # Larger sprite should create wider panel
        assert large_width > small_width

    def test_whitespace_only_text_treated_as_empty(self):
        """Test that whitespace-only text is treated as empty."""
        sprite_size = QtCore.QSize(200, 200)
        whitespace = "   \n\t  "

        width, height = WindowLayoutManager.compute_panel_size_hint(sprite_size, whitespace)

        # Should be same as empty text
        empty_width, empty_height = WindowLayoutManager.compute_panel_size_hint(
            sprite_size, ""
        )
        assert width == empty_width
        assert height == empty_height

    def test_minimum_constraints_enforced(self):
        """Test that minimum width/height constraints are enforced."""
        tiny_sprite = QtCore.QSize(10, 10)
        text = ""

        width, height = WindowLayoutManager.compute_panel_size_hint(tiny_sprite, text)

        # Should enforce minimums even with tiny sprite
        assert width >= 160.0
        assert height >= 80.0

    def test_multiline_text_wrapped_correctly(self):
        """Test that multiline text is calculated correctly."""
        sprite_size = QtCore.QSize(200, 200)
        # Text with explicit newlines
        multiline = "Line 1\nLine 2\nLine 3\nLine 4"

        width, height = WindowLayoutManager.compute_panel_size_hint(sprite_size, multiline)

        # Should be taller than single line
        single_width, single_height = WindowLayoutManager.compute_panel_size_hint(
            sprite_size, "Single"
        )
        assert height > single_height
