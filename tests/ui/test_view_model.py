"""Tests for DoroViewModel - presentation logic without UI coupling."""

import math
import pytest
from PySide6 import QtCore, QtGui

from doro_app.ui.view_model import DoroViewModel


class TestDoroViewModelInitialization:
    """Test ViewModel initialization."""

    def test_creates_with_default_values(self):
        """Test ViewModel initializes with sensible defaults."""
        vm = DoroViewModel()

        # Animation defaults
        assert vm.time == 0.0
        assert vm.bob_amplitude == 0.0
        assert vm.scale_amplitude == 0.0

        # Visual defaults
        assert len(vm.fill_colors) == 3
        assert vm.cheek_alpha == 0.0
        assert isinstance(vm.blush_color, QtGui.QColor)
        assert isinstance(vm.eye_color, QtGui.QColor)

        # Bubble defaults
        assert vm.bubble_visible is True
        assert vm.bubble_alpha == 255
        assert vm.bubble_side == "center"
        assert isinstance(vm.bubble_offset, QtCore.QPointF)
        assert vm.bubble_scale == 1.0

        # Sprite defaults
        assert isinstance(vm.sprite_size, QtCore.QSize)
        assert vm.sprite_offset_x == -110.0

        # Name tag
        assert vm.name_tag == "doro"

    def test_multiple_instances_have_independent_state(self):
        """Test that multiple ViewModel instances don't share mutable defaults.

        This is a regression test for the dataclass mutable default bug.
        Before the fix, QColor/QPointF/QSize defaults were shared across instances.
        """
        vm1 = DoroViewModel()
        vm2 = DoroViewModel()

        # Modify vm1's colors
        vm1.set_blush_color(QtGui.QColor(255, 0, 0))
        vm1.set_eye_color(QtGui.QColor(0, 255, 0))

        # vm2 should still have default colors (not affected by vm1)
        assert vm2.blush_color == QtGui.QColor(255, 150, 150)
        assert vm2.eye_color == QtGui.QColor(50, 50, 50)

        # Modify vm1's bubble offset
        vm1.set_bubble_offset(QtCore.QPointF(100.0, 200.0))

        # vm2 should still have default offset
        assert vm2.bubble_offset == QtCore.QPointF(0.0, 0.0)

        # Modify vm1's sprite size
        vm1.set_sprite_size(QtCore.QSize(500, 500))

        # vm2 should still have default size
        assert vm2.sprite_size == QtCore.QSize(200, 200)


class TestAnimationLogic:
    """Test animation time and calculations."""

    def test_tick_updates_time(self):
        """Test tick() advances animation time."""
        vm = DoroViewModel()

        vm.tick(0.016)  # ~60 FPS
        assert vm.time == pytest.approx(0.016)

        vm.tick(0.016)
        assert vm.time == pytest.approx(0.032)

    def test_calculate_bob_returns_zero_when_no_amplitude(self):
        """Test bob calculation returns 0 when amplitude is 0."""
        vm = DoroViewModel()
        vm.set_bob_amplitude(0.0)

        bob = vm.calculate_bob()
        assert bob == 0.0

    def test_calculate_bob_oscillates(self):
        """Test bob calculation creates oscillation."""
        vm = DoroViewModel()
        vm.set_bob_amplitude(10.0)

        # At time 0, sin(0) = 0
        bob_at_0 = vm.calculate_bob()
        assert bob_at_0 == 0.0

        # Advance time to π/4 radians (where sin is positive)
        vm.tick(math.pi / 8.0)  # time * 2.0 = π/4
        bob_positive = vm.calculate_bob()
        assert bob_positive > 0.0
        assert bob_positive == pytest.approx(10.0 * math.sin(math.pi / 4.0))

        # Advance to π/2 (actual peak where sin = 1.0)
        vm.reset_animation_time()
        vm.tick(math.pi / 4.0)  # time * 2.0 = π/2
        bob_peak = vm.calculate_bob()
        assert bob_peak == pytest.approx(10.0)  # amplitude * sin(π/2) = 10 * 1 = 10
        assert bob_peak > bob_positive

        # Advance past π (sine becomes negative)
        vm.reset_animation_time()
        vm.tick(3 * math.pi / 4.0)  # time * 2.0 = 3π/2
        bob_negative = vm.calculate_bob()
        assert bob_negative < 0.0
        assert bob_negative == pytest.approx(-10.0)  # sin(3π/2) = -1

    def test_calculate_scale_returns_one_when_no_amplitude(self):
        """Test scale calculation returns 1.0 when amplitude is 0."""
        vm = DoroViewModel()
        vm.set_scale_amplitude(0.0)

        scale = vm.calculate_scale()
        assert scale == 1.0

    def test_calculate_scale_oscillates_around_one(self):
        """Test scale calculation oscillates around 1.0."""
        vm = DoroViewModel()
        vm.set_scale_amplitude(0.1)

        # At time 0, sin(0) = 0, scale = 1.0
        scale_at_0 = vm.calculate_scale()
        assert scale_at_0 == pytest.approx(1.0)

        # Advance time
        vm.tick(math.pi / 8.0)
        scale_positive = vm.calculate_scale()
        assert scale_positive > 1.0

        # Advance past π (sine becomes negative)
        vm.reset_animation_time()
        vm.tick(3 * math.pi / 4.0)
        scale_negative = vm.calculate_scale()
        assert scale_negative < 1.0


class TestVisualConfiguration:
    """Test visual state management."""

    def test_set_and_get_fill_colors(self):
        """Test setting fill gradient colors."""
        vm = DoroViewModel()

        top = QtGui.QColor(255, 0, 0)
        mid = QtGui.QColor(0, 255, 0)
        bottom = QtGui.QColor(0, 0, 255)

        vm.set_fill_colors(top, mid, bottom)

        colors = vm.fill_colors
        assert colors[0] == top
        assert colors[1] == mid
        assert colors[2] == bottom

    def test_set_and_get_cheek_alpha(self):
        """Test setting cheek alpha."""
        vm = DoroViewModel()

        vm.set_cheek_alpha(128.0)
        assert vm.cheek_alpha == 128.0

    def test_set_and_get_blush_color(self):
        """Test setting blush color."""
        vm = DoroViewModel()

        color = QtGui.QColor(200, 100, 100)
        vm.set_blush_color(color)
        assert vm.blush_color == color

    def test_set_and_get_eye_color(self):
        """Test setting eye color."""
        vm = DoroViewModel()

        color = QtGui.QColor(50, 50, 200)
        vm.set_eye_color(color)
        assert vm.eye_color == color


class TestBubbleState:
    """Test bubble state management."""

    def test_set_and_get_bubble_visible(self):
        """Test bubble visibility toggle."""
        vm = DoroViewModel()

        vm.set_bubble_visible(False)
        assert vm.bubble_visible is False

        vm.set_bubble_visible(True)
        assert vm.bubble_visible is True

    def test_set_and_get_bubble_alpha(self):
        """Test bubble alpha setting."""
        vm = DoroViewModel()

        vm.set_bubble_alpha(128)
        assert vm.bubble_alpha == 128

    def test_bubble_alpha_clamps_to_valid_range(self):
        """Test bubble alpha is clamped to 0-255."""
        vm = DoroViewModel()

        vm.set_bubble_alpha(300)
        assert vm.bubble_alpha == 255

        vm.set_bubble_alpha(-10)
        assert vm.bubble_alpha == 0

    def test_set_and_get_bubble_side(self):
        """Test bubble side position."""
        vm = DoroViewModel()

        vm.set_bubble_side("left")
        assert vm.bubble_side == "left"

        vm.set_bubble_side("right")
        assert vm.bubble_side == "right"

    def test_set_and_get_bubble_offset(self):
        """Test bubble position offset."""
        vm = DoroViewModel()

        offset = QtCore.QPointF(10.0, 20.0)
        vm.set_bubble_offset(offset)
        assert vm.bubble_offset == offset

    def test_set_and_get_bubble_scale(self):
        """Test bubble scale multiplier."""
        vm = DoroViewModel()

        vm.set_bubble_scale(1.5)
        assert vm.bubble_scale == 1.5

    def test_bubble_scale_prevents_negative_values(self):
        """Test bubble scale is clamped to minimum 0.1."""
        vm = DoroViewModel()

        vm.set_bubble_scale(-1.0)
        assert vm.bubble_scale == 0.1

        vm.set_bubble_scale(0.0)
        assert vm.bubble_scale == 0.1


class TestSpriteState:
    """Test sprite state management."""

    def test_set_and_get_sprite_size(self):
        """Test sprite size setting."""
        vm = DoroViewModel()

        size = QtCore.QSize(300, 300)
        vm.set_sprite_size(size)
        assert vm.sprite_size == size

    def test_set_and_get_sprite_offset_x(self):
        """Test sprite horizontal offset."""
        vm = DoroViewModel()

        vm.set_sprite_offset_x(-50.0)
        assert vm.sprite_offset_x == -50.0


class TestNameTag:
    """Test name tag management."""

    def test_set_and_get_name_tag(self):
        """Test name tag text."""
        vm = DoroViewModel()

        vm.set_name_tag("custom_name")
        assert vm.name_tag == "custom_name"


class TestAnimationReset:
    """Test animation reset functionality."""

    def test_reset_animation_time(self):
        """Test reset clears animation time."""
        vm = DoroViewModel()

        vm.tick(1.0)
        assert vm.time == 1.0

        vm.reset_animation_time()
        assert vm.time == 0.0
