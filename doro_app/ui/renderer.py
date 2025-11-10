"""Rendering and animation helpers for :mod:`doro_app.window`."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

if TYPE_CHECKING:
    from ..bubble_controller import BubbleController
    from ..movement_manager import MovementManager
    from ..window import DoroWindow


class WindowRenderer:
    """Encapsulate drawing and animation ticks for :class:`DoroWindow`."""

    def __init__(self, window: DoroWindow, bubble: BubbleController, movement: MovementManager):
        self._window = window
        self._bubble = bubble
        self._movement = movement

    # ------------------------------------------------------------------ Timing

    def tick(self) -> None:
        window = self._window
        now = time.monotonic()
        dt = now - getattr(window, "_last_tick_time", now)
        window._last_tick_time = now
        if dt < 0.0:
            dt = 0.0
        dt = min(dt, 0.1)
        self._movement.process_active_movement(dt)
        window._t += dt
        window.update()

    def reset_clock(self) -> None:
        self._window._last_tick_time = time.monotonic()

    # ------------------------------------------------------------------ Painting

    def paint(self) -> None:
        window = self._window
        painter = QtGui.QPainter(window)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        bob = 0.0
        scale = 1.0

        sprite_center = self._sprite_center()
        painter.save()
        painter.translate(sprite_center.x(), sprite_center.y() + bob)
        painter.scale(scale, scale)

        movie = window._gif_movie
        if movie and not movie.currentPixmap().isNull():
            pixmap = movie.currentPixmap()
            painter.translate(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            painter.drawPixmap(0, 0, pixmap)
        else:
            painter.translate(-90, -90)

            path = QtGui.QPainterPath(QtCore.QPointF(90, 20))
            path.cubicTo(50, 20, 30, 50, 30, 90)
            path.cubicTo(30, 130, 50, 160, 90, 160)
            path.cubicTo(130, 160, 150, 130, 150, 90)
            path.cubicTo(150, 50, 130, 20, 90, 20)

            fill = QtGui.QLinearGradient(QtCore.QPointF(90, 20), QtCore.QPointF(90, 160))
            fill.setColorAt(0.0, window._fill_colors[0])
            fill.setColorAt(0.4, window._fill_colors[1])
            fill.setColorAt(1.0, window._fill_colors[2])

            painter.setPen(QtGui.QPen(QtGui.QColor("#FF5C9ED6"), 3))
            painter.setBrush(QtGui.QBrush(fill))
            painter.drawPath(path)

            if window._cheek_alpha > 0:
                blush = QtGui.QColor(window._blush_base)
                blush.setAlpha(int(window._cheek_alpha))
                painter.setBrush(blush)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.drawEllipse(QtCore.QRectF(55, 85, 18, 10))
                painter.drawEllipse(QtCore.QRectF(107, 85, 18, 10))

            painter.setBrush(window._eye_color)
            painter.drawEllipse(QtCore.QRectF(70, 70, 10, 14))
            painter.drawEllipse(QtCore.QRectF(100, 70, 10, 14))

            self._draw_mouth(painter)

        painter.restore()

        panel_should_draw = (
            (window._bubble_visible or window._bubble_text_show_override)
            and window._bubble_alpha > 0
            and bool((window._bubble_text or "").strip())
        )
        if panel_should_draw:
            alpha = min(max(int(window._bubble_alpha), 0), 255)
            self._draw_text_panel(painter, alpha)
        else:
            window._panel_rect_cache = None

        font = QtGui.QFont()
        font.setPointSize(10)
        font.setWeight(QtGui.QFont.Weight.Bold)
        painter.setFont(font)

    # ------------------------------------------------------------------ Helpers

    def _sprite_center(self) -> QtCore.QPointF:
        window = self._window
        base_x = window.width() / 2.0 + getattr(window, "_sprite_offset_x", 0.0)
        half_w = max(20.0, window._sprite_size.width() / 2.0)
        half_h = max(20.0, window._sprite_size.height() / 2.0)
        margin_x = 12.0
        min_center_x = half_w + margin_x
        max_center_x = window.width() - half_w - margin_x
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))
        bob_allowance = abs(getattr(window, "_amplitude", 0.0)) + 20.0
        margin_bottom = 24.0
        min_center_y = half_h + bob_allowance
        max_center_y = window.height() - half_h - margin_bottom
        if max_center_y < min_center_y:
            max_center_y = min_center_y
        if getattr(window, "_sprite_anchor_top", None) is None:
            panel_reserve = getattr(window, "_panel_height_hint", 110.0) + 48.0
            initial_base_y = (window.height() - panel_reserve) / 2.0
            initial_base_y = max(min_center_y, min(max_center_y, initial_base_y))
            window._sprite_anchor_top = max(0.0, initial_base_y - half_h)
        anchor_top = max(0.0, float(window._sprite_anchor_top or 0.0))
        base_y = anchor_top + half_h
        clamped_base_y = max(min_center_y, min(max_center_y, base_y))
        if clamped_base_y != base_y:
            anchor_top = max(0.0, clamped_base_y - half_h)
            window._sprite_anchor_top = anchor_top
            base_y = anchor_top + half_h
        return QtCore.QPointF(base_x, base_y)

    def _compute_panel_size_hint(self) -> tuple[float, float]:
        window = self._window
        text = (window._bubble_text or "").strip()
        sprite_w = max(120.0, float(window._sprite_size.width()))
        panel_width = max(160.0, sprite_w)
        available_text_width = max(80.0, panel_width - 56.0)

        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.Bold)
        metrics = QtGui.QFontMetrics(font)

        if text:
            flags = int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
            flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
            text_rect = metrics.boundingRect(
                QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
                flags,
                text,
            )
            text_height = float(text_rect.height())
        else:
            text_height = float(metrics.lineSpacing())

        panel_height = max(80.0, text_height + 56.0)
        return panel_width, panel_height

    def apply_window_preferred_size(self) -> None:
        window = self._window
        sprite_w = max(120.0, float(window._sprite_size.width()))
        sprite_h = max(120.0, float(window._sprite_size.height()))
        panel_w_hint, panel_h_hint = self._compute_panel_size_hint()
        window._panel_width_hint = panel_w_hint
        window._panel_height_hint = panel_h_hint

        desired_w = max(
            380,
            int(round(max(sprite_w + 120.0, panel_w_hint + 48.0))),
        )
        desired_h = max(
            320,
            int(round(sprite_h + panel_h_hint + 120.0)),
        )
        current_size = window.size()
        min_size = window.minimumSize()
        min_changed = min_size.width() != desired_w or min_size.height() != desired_h
        needs_resize = current_size.width() < desired_w or current_size.height() < desired_h

        if min_changed or needs_resize:
            window._sizing_in_progress = True
            try:
                if min_changed:
                    window.setMinimumSize(desired_w, desired_h)
                if needs_resize:
                    window.resize(
                        max(current_size.width(), desired_w),
                        max(current_size.height(), desired_h),
                    )
            finally:
                window._sizing_in_progress = False
        window.update()

    def update_sprite_size_hint(self, movie: QtGui.QMovie | None) -> None:
        window = self._window
        if movie and movie.isValid():
            rect = movie.frameRect()
            if rect.width() > 0 and rect.height() > 0:
                window._sprite_size = rect.size()
                self.apply_window_preferred_size()
                return
        window._sprite_size = QtCore.QSize(200, 200)
        self.apply_window_preferred_size()

    def apply_state_settings(self) -> None:
        window = self._window
        if window._state_settings is None:
            return
        window._amplitude = float(window._state_settings.bob_amplitude)
        window._scale_amp = float(window._state_settings.scale_amplitude)
        window._fill_colors = tuple(
            QtGui.QColor(color)
            for color in (
                window._state_settings.gradient_top,
                window._state_settings.gradient_mid,
                window._state_settings.gradient_bottom,
            )
        )
        window._cheek_alpha = float(window._state_settings.cheeks_alpha)
        window._blush_base = QtGui.QColor(window._state_settings.blush_color)
        window._eye_color = QtGui.QColor(window._state_settings.eye_color)
        window._bubble_visible = bool(window._state_settings.bubble_visible)
        window._bubble_alpha = float(window._state_settings.bubble_alpha)
        window._name_tag = window._state_settings.name_tag

        def _canonical_if_exists(path_str: str | None) -> str | None:
            if not path_str:
                return None
            try:
                path_obj = Path(path_str)
            except (TypeError, ValueError):
                return None
            if not path_obj.is_file():
                return None
            try:
                return str(path_obj.resolve())
            except OSError:
                return str(path_obj)

        primary_existing = _canonical_if_exists(window._state_settings.gif_path)
        active_existing = _canonical_if_exists(window._active_gif_path)

        gif_path = active_existing or primary_existing
        if gif_path is None:
            if window._default_idle_gif.is_file():
                try:
                    default_path = str(window._default_idle_gif.resolve())
                except OSError:
                    default_path = str(window._default_idle_gif)
                gif_path = default_path
                window._state_settings.gif_path = default_path
                primary_existing = default_path
                active_existing = None
            else:
                window._state_settings.gif_path = None

        if gif_path:
            if primary_existing and gif_path == primary_existing:
                if window._state_settings.gif_path != primary_existing:
                    window._state_settings.gif_path = primary_existing
                window._active_gif_path = None
            else:
                window._active_gif_path = active_existing if active_existing else None
        else:
            window._active_gif_path = None

        self.load_gif(gif_path)

    def load_gif(self, path: str | None) -> None:
        window = self._window
        movie = window._gif_movie
        if movie:
            try:
                movie.frameChanged.disconnect(self._on_movie_frame_changed)
            except (RuntimeError, TypeError):
                pass
            movie.stop()
            window._gif_movie = None

        if not path:
            self.update_sprite_size_hint(None)
            return

        path_obj = Path(path)
        if not path_obj.is_file():
            self.update_sprite_size_hint(None)
            return

        movie = QtGui.QMovie(str(path_obj))
        if not movie.isValid():
            self.update_sprite_size_hint(None)
            return

        movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(self._on_movie_frame_changed)
        movie.start()
        window._gif_movie = movie
        self.update_sprite_size_hint(movie)

    def on_movie_frame_changed(self, frame: int) -> None:
        self._on_movie_frame_changed(frame)

    def _on_movie_frame_changed(self, _frame: int) -> None:
        window = self._window
        movie = window._gif_movie
        if movie:
            pixmap = movie.currentPixmap()
            if not pixmap.isNull():
                frame_size = pixmap.size()
                if frame_size != window._sprite_size:
                    window._sprite_size = QtCore.QSize(frame_size)
                    self.apply_window_preferred_size()
        window.update()

    def set_bubble_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ) -> None:
        self._bubble.set_text(
            text,
            override_visibility=override_visibility,
            auto_hide=auto_hide,
            hide_delay_ms=hide_delay_ms,
        )
        self.apply_window_preferred_size()

    def clear_bubble_text(self) -> None:
        self._bubble.clear_text()

    # ------------------------------------------------------------------ Panel drawing

    def _draw_text_panel(self, painter: QtGui.QPainter, alpha: int) -> None:
        window = self._window
        text = (window._bubble_text or "").strip()
        if not text or alpha <= 0:
            window._panel_rect_cache = None
            return

        target_width = max(160.0, float(window._sprite_size.width()))
        panel_width = max(
            80.0,
            min(target_width, float(window.width()) - 24.0),
        )

        inner_padding_x = 28.0
        inner_padding_y = 22.0
        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        metrics = QtGui.QFontMetrics(font)
        text_flags = int(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        text_flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
        available_text_width = max(60.0, panel_width - inner_padding_x * 2.0)
        text_metrics = metrics.boundingRect(
            QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
            text_flags,
            text,
        )
        text_height = max(float(metrics.lineSpacing()), float(text_metrics.height()))
        panel_height = max(window._panel_height_hint, text_height + inner_padding_y * 2.0)

        sprite_center = self._sprite_center()
        sprite_half_h = float(max(20.0, window._sprite_size.height() / 2.0))
        gap = 28.0
        margin_top = 18.0
        margin_bottom = 24.0

        below_top = sprite_center.y() + sprite_half_h + gap
        available_below = window.height() - margin_bottom - below_top
        above_bottom = sprite_center.y() - sprite_half_h - gap
        available_above = max(0.0, above_bottom - margin_top)

        place_below = True
        adjusted_panel_height = panel_height

        if available_below < adjusted_panel_height and available_above > available_below:
            adjusted_panel_height = min(adjusted_panel_height, available_above)
            place_below = False
        else:
            adjusted_panel_height = min(adjusted_panel_height, max(available_below, 0.0))
            if adjusted_panel_height <= 0.0 and available_above > 0.0:
                adjusted_panel_height = min(panel_height, available_above)
                place_below = False

        if adjusted_panel_height <= 0.0:
            adjusted_panel_height = min(panel_height, window.height() - margin_top - margin_bottom)

        if place_below:
            top = max(margin_top, below_top)
            if top + adjusted_panel_height + margin_bottom > window.height():
                adjusted_panel_height = max(0.0, window.height() - margin_bottom - top)
            window._bubble_side = "below"
        else:
            bottom_edge = min(above_bottom, window.height() - margin_bottom)
            top = max(margin_top, bottom_edge - adjusted_panel_height)
            window._bubble_side = "above"

        if adjusted_panel_height <= 0.0:
            window._panel_rect_cache = None
            return

        left = sprite_center.x() - panel_width / 2.0
        min_left = 12.0
        max_left = window.width() - panel_width - 12.0
        if max_left < min_left:
            min_left = max_left = max(window.width() - panel_width, 0.0)
        left = max(min_left, min(max_left, left))
        panel_rect = QtCore.QRectF(left, top, panel_width, adjusted_panel_height)

        shadow_rect = panel_rect.adjusted(0.0, 8.0 if place_below else -12.0, 0.0, 12.0 if place_below else 4.0)
        corner_radius = 18.0

        base_alpha = max(140, min(255, alpha))
        outline_alpha = int(base_alpha * 0.55)
        fill_alpha = int(base_alpha * 0.92)

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

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        shadow_color = QtGui.QColor(4, 8, 20, int(base_alpha * 0.4))
        shadow_path = QtGui.QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, corner_radius, corner_radius)
        painter.fillPath(shadow_path, shadow_color)

        panel_path = QtGui.QPainterPath()
        panel_path.addRoundedRect(panel_rect, corner_radius, corner_radius)

        painter.setBrush(QtGui.QBrush(fill_gradient))
        outline_pen = QtGui.QPen(QtGui.QBrush(outline_gradient), 2.6)
        outline_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.drawPath(panel_path)

        sheen_shape = panel_path.intersected(sheen_clip)
        if not sheen_shape.isEmpty():
            painter.setBrush(QtGui.QBrush(sheen_gradient))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPath(sheen_shape)

        text_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 255))

        painter.setFont(font)
        painter.setPen(text_pen)
        painter.drawText(text_rect, text, text_option)

        painter.restore()
        window._panel_rect_cache = QtCore.QRectF(panel_rect)

    def _draw_mouth(self, painter: QtGui.QPainter) -> None:
        pen = QtGui.QPen(QtGui.QColor(51, 51, 51))
        pen.setWidthF(2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

        mouth = QtGui.QPainterPath()
        mouth.moveTo(80, 95)
        mouth.cubicTo(90, 105, 100, 105, 110, 95)
        painter.drawPath(mouth)
