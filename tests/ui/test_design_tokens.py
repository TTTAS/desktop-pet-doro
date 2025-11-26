"""Tests for design tokens."""

import pytest

from doro_app.ui.rendering.design_tokens import DesignTokens, tokens


class TestDesignTokens:
    """Tests for DesignTokens and token calculations."""

    def test_spacing_tokens_exist(self):
        """Test that spacing tokens are defined."""
        assert tokens.spacing.bubble_inner_x == 28.0
        assert tokens.spacing.bubble_inner_y == 22.0
        assert tokens.spacing.sprite_bubble_gap == 28.0
        assert tokens.spacing.margin_top == 18.0

    def test_radius_tokens_exist(self):
        """Test that border radius tokens are defined."""
        assert tokens.radius.bubble == 18.0
        assert tokens.radius.button == 8.0
        assert tokens.radius.dialog == 12.0

    def test_opacity_tokens_exist(self):
        """Test that opacity tokens are defined."""
        assert tokens.opacity.min_base_alpha == 140
        assert tokens.opacity.max_base_alpha == 255
        assert tokens.opacity.outline_multiplier == 0.55
        assert tokens.opacity.fill_multiplier == 0.92

    def test_animation_tokens_exist(self):
        """Test that animation tokens are defined."""
        assert tokens.animation.max_delta_time == 0.1
        assert tokens.animation.bob_amplitude_default == 8.0

    def test_sprite_size_tokens_exist(self):
        """Test that sprite size tokens are defined."""
        assert tokens.sprite.min_half_height == 20.0
        assert tokens.sprite.default_width == 128

    def test_bubble_size_tokens_exist(self):
        """Test that bubble size tokens are defined."""
        assert tokens.bubble.min_width == 180.0
        assert tokens.bubble.max_width == 400.0
        assert tokens.bubble.preferred_width == 280.0

    def test_gif_preview_tokens_exist(self):
        """Test that GIF preview tokens are defined."""
        assert tokens.gif.table_preview_size == 96
        assert tokens.gif.dialog_preview_size == 180

    def test_calculate_outline_alpha(self):
        """Test outline alpha calculation."""
        # Normal case
        assert DesignTokens.calculate_outline_alpha(200) == int(200 * 0.55)

        # Clamped minimum
        assert DesignTokens.calculate_outline_alpha(100) == int(140 * 0.55)

        # Clamped maximum
        assert DesignTokens.calculate_outline_alpha(300) == int(255 * 0.55)

    def test_calculate_fill_alpha(self):
        """Test fill alpha calculation."""
        # Normal case
        assert DesignTokens.calculate_fill_alpha(200) == int(200 * 0.92)

        # Clamped minimum
        assert DesignTokens.calculate_fill_alpha(100) == int(140 * 0.92)

        # Clamped maximum
        assert DesignTokens.calculate_fill_alpha(300) == int(255 * 0.92)

    def test_calculate_shadow_alpha(self):
        """Test shadow alpha calculation."""
        # Normal case
        assert DesignTokens.calculate_shadow_alpha(200) == int(200 * 0.25)

        # Clamped minimum
        assert DesignTokens.calculate_shadow_alpha(100) == int(140 * 0.25)

        # Clamped maximum
        assert DesignTokens.calculate_shadow_alpha(300) == int(255 * 0.25)

    def test_tokens_are_immutable(self):
        """Test that tokens are frozen (immutable)."""
        with pytest.raises(AttributeError):
            tokens.spacing.bubble_inner_x = 50.0  # type: ignore

        with pytest.raises(AttributeError):
            tokens.radius.bubble = 20.0  # type: ignore

    def test_singleton_instance(self):
        """Test that tokens is a singleton instance."""
        assert isinstance(tokens, DesignTokens)
        assert tokens.spacing is DesignTokens.spacing
