"""Rendering engine for Doro sprite and text panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from ...constants import (
    SPRITE_BOB_ALLOWANCE,
    SPRITE_MARGIN_BOTTOM,
    SPRITE_MARGIN_X,
    SPRITE_MIN_SIZE,
)
from ..viewmodels.doro_viewmodel import DoroViewModel
from .design_tokens import tokens

if TYPE_CHECKING:
    from .sprite_renderer import SpriteRenderer


class RenderingEngine:
    """
    Handles layout calculation and text-panel rendering.

    Sprite rendering is delegated to a SpriteRenderer implementation.
    This class does not depend on DoroWindow, only on ViewModel.
    """

    def __init__(self, view_model: DoroViewModel):
        """
        Initialize the rendering engine.

        Args:
            view_model: ViewModel containing presentation state
        """
        self._view_model = view_model
        self._panel_font = self._make_panel_font()

    @staticmethod
    def _make_panel_font() -> QtGui.QFont:
        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        return font

    def calculate_sprite_center(
        self,
        window_size: QtCore.QSize,
        sprite_anchor_top: float | None,
    ) -> tuple[QtCore.QPointF, float | None]:
        """
        Calculate sprite center position within the window.

        Doro's window is normally exactly sprite-sized (the speech bubble has its
        own window), so the sprite fills it. A larger window — only briefly, before
        the first layout — centres the sprite within margins.

        Returns:
            Tuple of (sprite_center_point, updated_sprite_anchor_top)
        """
        half_w = max(SPRITE_MIN_SIZE, self._view_model.sprite_size.width() / 2.0)
        half_h = max(SPRITE_MIN_SIZE, self._view_model.sprite_size.height() / 2.0)

        sprite_w = self._view_model.sprite_size.width()
        sprite_h = self._view_model.sprite_size.height()
        if window_size.width() <= sprite_w + 1 and window_size.height() <= sprite_h + 1:
            center = QtCore.QPointF(window_size.width() / 2.0, window_size.height() / 2.0)
            return center, max(0.0, center.y() - half_h)

        base_x = window_size.width() / 2.0 + self._view_model.sprite_offset_x
        min_center_x = half_w + SPRITE_MARGIN_X
        max_center_x = window_size.width() - half_w - SPRITE_MARGIN_X
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))

        bob_allowance = abs(self._view_model.bob_amplitude) + SPRITE_BOB_ALLOWANCE
        min_center_y = half_h + bob_allowance
        max_center_y = max(window_size.height() - half_h - SPRITE_MARGIN_BOTTOM, min_center_y)

        if sprite_anchor_top is None:
            initial_base_y = max(min_center_y, min(max_center_y, window_size.height() / 2.0))
            sprite_anchor_top = max(0.0, initial_base_y - half_h)

        anchor_top = max(0.0, float(sprite_anchor_top or 0.0))
        base_y = anchor_top + half_h
        clamped_base_y = max(min_center_y, min(max_center_y, base_y))
        if clamped_base_y != base_y:
            anchor_top = max(0.0, clamped_base_y - half_h)
            sprite_anchor_top = anchor_top
            base_y = anchor_top + half_h

        return QtCore.QPointF(base_x, base_y), sprite_anchor_top

    def render_sprite(
        self,
        painter: QtGui.QPainter,
        sprite_renderer: SpriteRenderer,
        sprite_center: QtCore.QPointF,
        bob: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        """
        Render the sprite via the supplied *sprite_renderer*.

        The renderer is responsible for drawing the character
        (GIF, Spine, or fallback) — this method only delegates.
        """
        sprite_renderer.render(painter, sprite_center, bob, scale)

    @property
    def panel_font(self) -> QtGui.QFont:
        """Font used for speech-bubble text (measuring and drawing must agree)."""
        return self._panel_font

    def draw_bubble(
        self,
        painter: QtGui.QPainter,
        panel_rect: QtCore.QRectF,
        bubble_text: str,
        alpha: int,
        *,
        below: bool,
    ) -> None:
        """Draw the speech bubble (shadow, panel, sheen, text) into ``panel_rect``.

        Placement is decided by the caller (the bubble now lives in its own
        window, see SpeechBubbleWindow); ``below`` only picks the shadow side.
        """
        text = bubble_text.strip()
        if not text or alpha <= 0 or panel_rect.isEmpty():
            return
        place_below = below
        font = self._panel_font
        inner_padding_x = tokens.spacing.bubble_inner_x
        inner_padding_y = tokens.spacing.bubble_inner_y

        # Shadow rect
        shadow_rect = panel_rect.adjusted(
            0.0,
            (
                tokens.spacing.shadow_offset_below
                if place_below
                else tokens.spacing.shadow_offset_above
            ),
            0.0,
            (
                tokens.spacing.shadow_extend_below
                if place_below
                else tokens.spacing.shadow_extend_above
            ),
        )
        corner_radius = tokens.radius.bubble

        # Alpha values
        base_alpha = max(tokens.opacity.min_base_alpha, min(tokens.opacity.max_base_alpha, alpha))
        outline_alpha = tokens.calculate_outline_alpha(base_alpha)
        fill_alpha = tokens.calculate_fill_alpha(base_alpha)

        # Gradients
        fill_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.left(), panel_rect.bottom()),
        )
        fill_gradient.setColorAt(0.0, QtGui.QColor(255, 255, 255, fill_alpha))
        fill_gradient.setColorAt(1.0, QtGui.QColor(236, 240, 255, fill_alpha))

        outline_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.right(), panel_rect.bottom()),
        )
        outline_gradient.setColorAt(0.0, QtGui.QColor(134, 180, 255, outline_alpha))
        outline_gradient.setColorAt(1.0, QtGui.QColor(255, 255, 255, outline_alpha))

        sheen_clip = QtGui.QPainterPath()
        sheen_clip.addRoundedRect(
            panel_rect.adjusted(12.0, 12.0, -12.0, -panel_rect.height() * 0.55),
            corner_radius - 6.0,
            corner_radius - 6.0,
        )
        sheen_gradient = QtGui.QLinearGradient(
            QtCore.QPointF(panel_rect.left(), panel_rect.top()),
            QtCore.QPointF(panel_rect.right(), panel_rect.top()),
        )
        sheen_gradient.setColorAt(0.0, QtGui.QColor(255, 255, 255, int(base_alpha * 0.28)))
        sheen_gradient.setColorAt(0.6, QtGui.QColor(255, 255, 255, int(base_alpha * 0.12)))
        sheen_gradient.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))

        text_rect = panel_rect.adjusted(
            inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y
        )
        text_option = QtGui.QTextOption(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        text_option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)

        # Render
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Shadow
        shadow_color = QtGui.QColor(4, 8, 20, int(base_alpha * 0.4))
        shadow_path = QtGui.QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, corner_radius, corner_radius)
        painter.fillPath(shadow_path, shadow_color)

        # Panel
        panel_path = QtGui.QPainterPath()
        panel_path.addRoundedRect(panel_rect, corner_radius, corner_radius)

        painter.setBrush(QtGui.QBrush(fill_gradient))
        outline_pen = QtGui.QPen(QtGui.QBrush(outline_gradient), 2.6)
        outline_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.drawPath(panel_path)

        # Sheen
        sheen_shape = panel_path.intersected(sheen_clip)
        if not sheen_shape.isEmpty():
            painter.setBrush(QtGui.QBrush(sheen_gradient))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPath(sheen_shape)

        # Text
        text_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 255))
        painter.setFont(font)
        painter.setPen(text_pen)
        painter.drawText(text_rect, text, text_option)

        painter.restore()
