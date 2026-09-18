"""DoroViewModel - Manages presentation state and animation logic.

This class separates presentation logic from the UI rendering layer,
making it testable without Qt dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui


@dataclass
class AnimationState:
    """Current animation state."""

    time: float = 0.0  # Animation clock
    bob_amplitude: float = 0.0  # Vertical bobbing
    scale_amplitude: float = 0.0  # Scale pulsing

    def tick(self, delta_time: float) -> None:
        """Update animation time."""
        self.time += delta_time


@dataclass
class VisualState:
    """Visual appearance configuration."""

    fill_colors: tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]
    cheek_alpha: float = 0.0
    blush_color: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 150, 150))
    eye_color: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(50, 50, 50))


@dataclass
class BubbleState:
    """Bubble (speech bubble) state."""

    visible: bool = True
    alpha: int = 255
    side: str = "center"  # "left", "right", "center"
    offset: QtCore.QPointF = field(default_factory=lambda: QtCore.QPointF(0.0, 0.0))
    scale: float = 1.0


@dataclass
class SpriteState:
    """Sprite appearance state."""

    size: QtCore.QSize = field(default_factory=lambda: QtCore.QSize(200, 200))
    offset_x: float = -110.0


class DoroViewModel:
    """
    Manages all presentation state and animation calculations.

    Responsibilities:
    - Store animation state (time, amplitude, etc.)
    - Store visual configuration (colors, alpha, etc.)
    - Calculate bob/scale based on time
    - Provide read-only access to state

    Does NOT:
    - Know about Qt widgets
    - Handle events
    - Render anything
    - Manage resources
    """

    def __init__(self):
        # Initialize default states
        default_fill = (
            QtGui.QColor(255, 220, 200),
            QtGui.QColor(255, 200, 180),
            QtGui.QColor(255, 180, 160),
        )

        self._animation = AnimationState()
        self._visual = VisualState(fill_colors=default_fill)
        self._bubble = BubbleState()
        self._sprite = SpriteState()

        self._name_tag: str = "doro"

    # ═══════════════════════════════════════════════════════════
    # Public API - Animation
    # ═══════════════════════════════════════════════════════════

    def tick(self, delta_time: float) -> None:
        """
        Update animation time.

        Args:
            delta_time: Time elapsed since last tick in seconds
        """
        self._animation.tick(delta_time)

    def calculate_bob(self) -> float:
        """
        Calculate vertical bobbing offset based on current animation time.

        Returns:
            Vertical offset in pixels
        """
        if self._animation.bob_amplitude <= 0.0:
            return 0.0

        # Sine wave for smooth bobbing
        return self._animation.bob_amplitude * math.sin(self._animation.time * 2.0)

    def calculate_scale(self) -> float:
        """
        Calculate scale multiplier based on current animation time.

        Returns:
            Scale multiplier (1.0 = normal size)
        """
        if self._animation.scale_amplitude <= 0.0:
            return 1.0

        # Sine wave for smooth scaling
        return 1.0 + self._animation.scale_amplitude * math.sin(self._animation.time * 2.0)

    # ═══════════════════════════════════════════════════════════
    # Public API - State Access (Read-Only)
    # ═══════════════════════════════════════════════════════════

    @property
    def time(self) -> float:
        """Get current animation time."""
        return self._animation.time

    @property
    def bob_amplitude(self) -> float:
        """Get current bob amplitude."""
        return self._animation.bob_amplitude

    @property
    def scale_amplitude(self) -> float:
        """Get current scale amplitude."""
        return self._animation.scale_amplitude

    @property
    def fill_colors(self) -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]:
        """Get fill gradient colors."""
        return self._visual.fill_colors

    @property
    def cheek_alpha(self) -> float:
        """Get cheek blush alpha."""
        return self._visual.cheek_alpha

    @property
    def blush_color(self) -> QtGui.QColor:
        """Get blush base color."""
        return self._visual.blush_color

    @property
    def eye_color(self) -> QtGui.QColor:
        """Get eye color."""
        return self._visual.eye_color

    @property
    def bubble_visible(self) -> bool:
        """Check if bubble is visible."""
        return self._bubble.visible

    @property
    def bubble_alpha(self) -> int:
        """Get bubble alpha value."""
        return self._bubble.alpha

    @property
    def bubble_side(self) -> str:
        """Get bubble side position."""
        return self._bubble.side

    @property
    def bubble_offset(self) -> QtCore.QPointF:
        """Get bubble position offset."""
        return self._bubble.offset

    @property
    def bubble_scale(self) -> float:
        """Get bubble scale multiplier."""
        return self._bubble.scale

    @property
    def sprite_size(self) -> QtCore.QSize:
        """Get sprite size."""
        return self._sprite.size

    @property
    def sprite_offset_x(self) -> float:
        """Get sprite horizontal offset."""
        return self._sprite.offset_x

    @property
    def name_tag(self) -> str:
        """Get name tag text."""
        return self._name_tag

    # ═══════════════════════════════════════════════════════════
    # Public API - State Mutation
    # ═══════════════════════════════════════════════════════════

    def set_bob_amplitude(self, amplitude: float) -> None:
        """Set bob animation amplitude."""
        self._animation.bob_amplitude = amplitude

    def set_scale_amplitude(self, amplitude: float) -> None:
        """Set scale animation amplitude."""
        self._animation.scale_amplitude = amplitude

    def set_fill_colors(self, top: QtGui.QColor, mid: QtGui.QColor, bottom: QtGui.QColor) -> None:
        """Set fill gradient colors."""
        self._visual.fill_colors = (top, mid, bottom)

    def set_cheek_alpha(self, alpha: float) -> None:
        """Set cheek blush alpha."""
        self._visual.cheek_alpha = alpha

    def set_blush_color(self, color: QtGui.QColor) -> None:
        """Set blush base color."""
        self._visual.blush_color = color

    def set_eye_color(self, color: QtGui.QColor) -> None:
        """Set eye color."""
        self._visual.eye_color = color

    def set_bubble_visible(self, visible: bool) -> None:
        """Set bubble visibility."""
        self._bubble.visible = visible

    def set_bubble_alpha(self, alpha: int) -> None:
        """Set bubble alpha value."""
        self._bubble.alpha = max(0, min(255, alpha))

    def set_bubble_side(self, side: str) -> None:
        """Set bubble side position."""
        self._bubble.side = side

    def set_bubble_offset(self, offset: QtCore.QPointF) -> None:
        """Set bubble position offset."""
        self._bubble.offset = offset

    def set_bubble_scale(self, scale: float) -> None:
        """Set bubble scale multiplier."""
        self._bubble.scale = max(0.1, scale)  # Prevent negative/zero scale

    def set_sprite_size(self, size: QtCore.QSize) -> None:
        """Set sprite size."""
        self._sprite.size = size

    def set_sprite_offset_x(self, offset: float) -> None:
        """Set sprite horizontal offset."""
        self._sprite.offset_x = offset

    def set_name_tag(self, name: str) -> None:
        """Set name tag text."""
        self._name_tag = name

    def reset_animation_time(self) -> None:
        """Reset animation clock to zero."""
        self._animation.time = 0.0
