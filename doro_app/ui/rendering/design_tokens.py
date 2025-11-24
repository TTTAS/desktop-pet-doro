"""Design tokens - centralized design constants.

This module contains all magic numbers used throughout the UI,
organized by category for easy maintenance and consistency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spacing:
    """Spacing and padding tokens."""

    # Bubble panel padding
    bubble_inner_x: float = 28.0
    bubble_inner_y: float = 22.0

    # Sprite-bubble spacing
    sprite_bubble_gap: float = 28.0

    # Window margins
    margin_top: float = 18.0
    margin_bottom: float = 24.0
    margin_horizontal: float = 12.0

    # Shadow adjustments
    shadow_offset_below: float = 8.0
    shadow_offset_above: float = -12.0
    shadow_extend_below: float = 12.0
    shadow_extend_above: float = 4.0


@dataclass(frozen=True)
class BorderRadius:
    """Border radius tokens."""

    bubble: float = 18.0
    button: float = 8.0
    dialog: float = 12.0


@dataclass(frozen=True)
class Opacity:
    """Opacity/alpha tokens (0-255 range)."""

    # Base alpha thresholds
    min_base_alpha: int = 140
    max_base_alpha: int = 255

    # Alpha multipliers (0.0-1.0)
    outline_multiplier: float = 0.55
    fill_multiplier: float = 0.92
    shadow_multiplier: float = 0.25


@dataclass(frozen=True)
class Animation:
    """Animation timing and parameters."""

    # Frame timing
    max_delta_time: float = 0.1  # seconds
    default_fps: int = 60

    # Bob (floating) parameters
    bob_amplitude_default: float = 8.0
    bob_frequency_default: float = 2.0

    # Scale (breathing) parameters
    scale_min: float = 0.95
    scale_max: float = 1.05
    scale_frequency: float = 1.5


@dataclass(frozen=True)
class SpriteSize:
    """Sprite size constraints."""

    min_half_height: float = 20.0
    default_width: int = 128
    default_height: int = 128


@dataclass(frozen=True)
class BubbleSize:
    """Bubble text panel size constraints."""

    # Width constraints
    min_width: float = 180.0
    max_width: float = 400.0
    preferred_width: float = 280.0

    # Height constraints
    min_height: float = 60.0

    # Text constraints
    max_display_lines: int = 3


@dataclass(frozen=True)
class GifPreview:
    """GIF preview sizes in dialogs."""

    # Table preview size
    table_preview_size: int = 96
    table_cell_size: int = 114

    # Dialog preview size
    dialog_preview_size: int = 180


class DesignTokens:
    """Centralized access to all design tokens."""

    spacing = Spacing()
    radius = BorderRadius()
    opacity = Opacity()
    animation = Animation()
    sprite = SpriteSize()
    bubble = BubbleSize()
    gif = GifPreview()

    @staticmethod
    def calculate_outline_alpha(base_alpha: int) -> int:
        """Calculate outline alpha from base alpha."""
        clamped = max(DesignTokens.opacity.min_base_alpha,
                     min(DesignTokens.opacity.max_base_alpha, base_alpha))
        return int(clamped * DesignTokens.opacity.outline_multiplier)

    @staticmethod
    def calculate_fill_alpha(base_alpha: int) -> int:
        """Calculate fill alpha from base alpha."""
        clamped = max(DesignTokens.opacity.min_base_alpha,
                     min(DesignTokens.opacity.max_base_alpha, base_alpha))
        return int(clamped * DesignTokens.opacity.fill_multiplier)

    @staticmethod
    def calculate_shadow_alpha(base_alpha: int) -> int:
        """Calculate shadow alpha from base alpha."""
        clamped = max(DesignTokens.opacity.min_base_alpha,
                     min(DesignTokens.opacity.max_base_alpha, base_alpha))
        return int(clamped * DesignTokens.opacity.shadow_multiplier)


# Singleton instance for easy import
tokens = DesignTokens()
