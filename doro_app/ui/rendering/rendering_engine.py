"""Rendering engine for Doro sprite and text panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from ..viewmodels.doro_viewmodel import DoroViewModel
from .design_tokens import tokens
from ...constants import (
    SPRITE_MIN_SIZE,
    SPRITE_MARGIN_X,
    SPRITE_MARGIN_BOTTOM,
    SPRITE_BOB_ALLOWANCE,
    SPRITE_PANEL_RESERVE_OFFSET,
    PANEL_DEFAULT_HEIGHT_HINT,
    PANEL_MIN_WIDTH,
    PANEL_MIN_HEIGHT,
    PANEL_MAX_WIDTH,
)

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

        Args:
            window_size: Current window size
            sprite_anchor_top: Current sprite anchor top position (None for initial calculation)

        Returns:
            Tuple of (sprite_center_point, updated_sprite_anchor_top)
        """
        base_x = window_size.width() / 2.0 + self._view_model.sprite_offset_x
        half_w = max(SPRITE_MIN_SIZE, self._view_model.sprite_size.width() / 2.0)
        half_h = max(SPRITE_MIN_SIZE, self._view_model.sprite_size.height() / 2.0)

        # Horizontal constraints
        margin_x = SPRITE_MARGIN_X
        min_center_x = half_w + margin_x
        max_center_x = window_size.width() - half_w - margin_x
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))

        # Vertical constraints
        bob_allowance = abs(self._view_model.bob_amplitude) + SPRITE_BOB_ALLOWANCE
        margin_bottom = SPRITE_MARGIN_BOTTOM
        min_center_y = half_h + bob_allowance
        max_center_y = window_size.height() - half_h - margin_bottom
        if max_center_y < min_center_y:
            max_center_y = min_center_y

        # Calculate or use existing anchor
        if sprite_anchor_top is None:
            panel_reserve = PANEL_DEFAULT_HEIGHT_HINT + SPRITE_PANEL_RESERVE_OFFSET
            initial_base_y = (window_size.height() - panel_reserve) / 2.0
            initial_base_y = max(min_center_y, min(max_center_y, initial_base_y))
            sprite_anchor_top = max(0.0, initial_base_y - half_h)

        anchor_top = max(0.0, float(sprite_anchor_top or 0.0))
        base_y = anchor_top + half_h
        clamped_base_y = max(min_center_y, min(max_center_y, base_y))

        # Update anchor if clamped
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

    def render_text_panel(
        self,
        painter: QtGui.QPainter,
        bubble_text: str,
        alpha: int,
        sprite_center: QtCore.QPointF,
        window_size: QtCore.QSize,
        panel_height_hint: float,
    ) -> QtCore.QRectF | None:
        """
        Render the text panel (bubble).

        Args:
            painter: Qt painter to render with
            bubble_text: Text to display
            alpha: Panel alpha (0-COLOR_ALPHA_MAX)
            sprite_center: Center position of sprite
            window_size: Current window size
            panel_height_hint: Panel height hint

        Returns:
            Panel rect if rendered, None otherwise
        """
        text = bubble_text.strip()
        if not text or alpha <= 0:
            return None

        # Calculate panel dimensions
        target_width = max(PANEL_MIN_WIDTH, float(self._view_model.sprite_size.width()))
        panel_width = max(
            PANEL_MIN_HEIGHT,
            min(target_width, float(window_size.width()) - 24.0),
        )

        inner_padding_x = tokens.spacing.bubble_inner_x
        inner_padding_y = tokens.spacing.bubble_inner_y

        font = self._panel_font
        metrics = QtGui.QFontMetrics(font)

        text_flags = int(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        text_flags |= int(QtCore.Qt.TextFlag.TextWordWrap)

        available_text_width = max(60.0, panel_width - inner_padding_x * 2.0)
        text_metrics = metrics.boundingRect(
            QtCore.QRect(0, 0, int(round(available_text_width)), int(PANEL_MAX_WIDTH)),
            text_flags,
            text,
        )
        text_height = max(float(metrics.lineSpacing()), float(text_metrics.height()))
        panel_height = max(panel_height_hint, text_height + inner_padding_y * 2.0)

        # Calculate panel position
        sprite_half_h = float(max(tokens.sprite.min_half_height, self._view_model.sprite_size.height() / 2.0))
        gap = tokens.spacing.sprite_bubble_gap
        margin_top = tokens.spacing.margin_top
        margin_bottom = tokens.spacing.margin_bottom

        below_top = sprite_center.y() + sprite_half_h + gap
        available_below = window_size.height() - margin_bottom - below_top
        above_bottom = sprite_center.y() - sprite_half_h - gap
        available_above = max(0.0, above_bottom - margin_top)

        place_below = True
        adjusted_panel_height = panel_height

        # Determine placement (below or above sprite)
        if available_below < adjusted_panel_height and available_above > available_below:
            adjusted_panel_height = min(adjusted_panel_height, available_above)
            place_below = False
        else:
            adjusted_panel_height = min(adjusted_panel_height, max(available_below, 0.0))
            if adjusted_panel_height <= 0.0 and available_above > 0.0:
                adjusted_panel_height = min(panel_height, available_above)
                place_below = False

        if adjusted_panel_height <= 0.0:
            adjusted_panel_height = min(panel_height, window_size.height() - margin_top - margin_bottom)

        # Calculate top position
        if place_below:
            top = max(margin_top, below_top)
            if top + adjusted_panel_height + margin_bottom > window_size.height():
                adjusted_panel_height = max(0.0, window_size.height() - margin_bottom - top)
            self._view_model.set_bubble_side("below")
        else:
            bottom_edge = min(above_bottom, window_size.height() - margin_bottom)
            top = max(margin_top, bottom_edge - adjusted_panel_height)
            self._view_model.set_bubble_side("above")

        if adjusted_panel_height <= 0.0:
            return None

        # Calculate left position
        left = sprite_center.x() - panel_width / 2.0
        min_left = tokens.spacing.margin_horizontal
        max_left = window_size.width() - panel_width - tokens.spacing.margin_horizontal
        if max_left < min_left:
            min_left = max_left = max(window_size.width() - panel_width, 0.0)
        left = max(min_left, min(max_left, left))

        panel_rect = QtCore.QRectF(left, top, panel_width, adjusted_panel_height)

        # Shadow rect
        shadow_rect = panel_rect.adjusted(
            0.0,
            tokens.spacing.shadow_offset_below if place_below else tokens.spacing.shadow_offset_above,
            0.0,
            tokens.spacing.shadow_extend_below if place_below else tokens.spacing.shadow_extend_above
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

        text_rect = panel_rect.adjusted(inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y)
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

        return QtCore.QRectF(panel_rect)
