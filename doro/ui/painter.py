from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


def _debug(widget, message: str):
    handler = getattr(widget, "_debug", None)
    if callable(handler):
        handler(message)


class UIRenderMixin:
    """Handles painting, GIF loading, and bubble rendering."""

    # --- Painting -------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        compat_enabled = bool(getattr(self, "_compat_window_enabled", False))
        if compat_enabled:
            palette = self.palette() if hasattr(self, "palette") else None
            base_color = (
                palette.color(QtGui.QPalette.ColorRole.Window)
                if palette
                else QtGui.QColor("#080f1d")
            )
            p.fillRect(self.rect(), base_color)

        movie = getattr(self, "_gif_movie", None)
        pixmap = QtGui.QPixmap()
        pixmap_ready = False
        if movie:
            pixmap = movie.currentPixmap()
            pixmap_ready = not pixmap.isNull()

        if not getattr(self, "_paint_debug_logged", False):
            self._paint_debug_logged = True
            _debug(
                self,
                (
                    f"paintEvent: size={self.width()}x{self.height()} "
                    f"movie={'yes' if movie else 'no'} "
                    f"pixmap_ready={pixmap_ready} compat={compat_enabled}"
                ),
            )

        bob = 0.0
        scale = 1.0

        sprite_center = self._sprite_center()
        p.save()
        p.translate(sprite_center.x(), sprite_center.y() + bob)
        p.scale(scale, scale)

        if pixmap_ready:
            if not getattr(self, "_debug_sprite_dumped", False):
                self._debug_sprite_dumped = True
                image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGBA8888)
                sample = QtGui.QColor(
                    image.pixel(
                        max(0, min(image.width() - 1, image.width() // 2)),
                        max(0, min(image.height() - 1, image.height() // 2)),
                    )
                )
                _debug(
                    self,
                    (
                        f"sprite sample rgba={sample.red()},{sample.green()},{sample.blue()},{sample.alpha()} "
                        f"size={image.width()}x{image.height()}"
                    ),
                )
                self._save_debug_image(image, "debug_sprite_frame.png")
            p.translate(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            p.drawPixmap(0, 0, pixmap)
        else:
            p.translate(-90, -90)

            path = QtGui.QPainterPath(QtCore.QPointF(90, 20))
            path.cubicTo(50, 20, 30, 50, 30, 90)
            path.cubicTo(30, 130, 50, 160, 90, 160)
            path.cubicTo(130, 160, 150, 130, 150, 90)
            path.cubicTo(150, 50, 130, 20, 90, 20)

            fill = QtGui.QLinearGradient(QtCore.QPointF(90, 20), QtCore.QPointF(90, 160))
            fill.setColorAt(0.0, self._fill_colors[0])
            fill.setColorAt(0.4, self._fill_colors[1])
            fill.setColorAt(1.0, self._fill_colors[2])

            p.setPen(QtGui.QPen(QtGui.QColor("#FF5C9ED6"), 3))
            p.setBrush(QtGui.QBrush(fill))
            p.drawPath(path)

            if self._cheek_alpha > 0:
                blush = QtGui.QColor(self._blush_base)
                blush.setAlpha(int(self._cheek_alpha))
                p.setBrush(blush)
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.drawEllipse(QtCore.QRectF(55, 85, 18, 10))
                p.drawEllipse(QtCore.QRectF(107, 85, 18, 10))

            p.setBrush(self._eye_color)
            p.drawEllipse(QtCore.QRectF(70, 70, 10, 14))
            p.drawEllipse(QtCore.QRectF(100, 70, 10, 14))

            self._draw_mouth(p)

        p.restore()

        bubble = getattr(self, "_bubble", None)
        panel_should_draw = (
            bubble
            and (bubble.visible or bubble.text_show_override)
            and bubble.alpha > 0
            and bool((bubble.text or "").strip())
        )
        if panel_should_draw and bubble:
            alpha = min(max(int(bubble.alpha), 0), 255)
            self._draw_text_panel(p, bubble, alpha)
        elif bubble:
            bubble.panel_rect = None

        font = QtGui.QFont()
        font.setPointSize(10)
        font.setWeight(QtGui.QFont.Weight.Bold)
        p.setFont(font)

    # --- Geometry helpers -----------------------------------------------
    def _sprite_center(self) -> QtCore.QPointF:
        base_x = self.width() / 2.0 + getattr(self, "_sprite_offset_x", 0.0)
        half_w = max(20.0, self._sprite_size.width() / 2.0)
        half_h = max(20.0, self._sprite_size.height() / 2.0)
        margin_x = 12.0
        min_center_x = half_w + margin_x
        max_center_x = self.width() - half_w - margin_x
        if min_center_x <= max_center_x:
            base_x = max(min_center_x, min(max_center_x, base_x))
        bob_allowance = abs(getattr(self, "_amplitude", 0.0)) + 20.0
        margin_bottom = 24.0
        min_center_y = half_h + bob_allowance
        max_center_y = self.height() - half_h - margin_bottom
        if max_center_y < min_center_y:
            max_center_y = min_center_y
        if getattr(self, "_sprite_anchor_top", None) is None:
            bubble = getattr(self, "_bubble", None)
            panel_hint = bubble.height_hint if bubble else 110.0
            panel_reserve = panel_hint + 48.0
            initial_base_y = (self.height() - panel_reserve) / 2.0
            initial_base_y = max(min_center_y, min(max_center_y, initial_base_y))
            self._sprite_anchor_top = max(0.0, initial_base_y - half_h)
        anchor_top = max(0.0, float(self._sprite_anchor_top or 0.0))
        base_y = anchor_top + half_h
        clamped_base_y = max(min_center_y, min(max_center_y, base_y))
        if clamped_base_y != base_y:
            anchor_top = max(0.0, clamped_base_y - half_h)
            self._sprite_anchor_top = anchor_top
            base_y = anchor_top + half_h
        return QtCore.QPointF(base_x, base_y)

    def _clamp_bubble_offset(self, candidate: QtCore.QPointF) -> QtCore.QPointF:
        bbox = QtCore.QRectF(-200.0, -220.0, 400.0, 300.0)
        clamped = QtCore.QPointF(
            max(bbox.left(), min(bbox.right(), candidate.x())),
            max(bbox.top(), min(bbox.bottom(), candidate.y())),
        )
        return clamped

    def _apply_bubble_offset(self, candidate: QtCore.QPointF, *, persist: bool = False):
        clamped = self._clamp_bubble_offset(candidate)
        bubble = getattr(self, "_bubble", None)
        if bubble:
            bubble.offset = clamped
            if persist:
                bubble.persist_preferences()

    def _bubble_handle_rect(self) -> QtCore.QRectF | None:
        bubble = getattr(self, "_bubble", None)
        rect = bubble.panel_rect if bubble else None
        if rect is None:
            return None
        handle = QtCore.QRectF(rect.right() - 28.0, rect.bottom() - 28.0, 24.0, 24.0)
        return handle

    def _available_screen_geometry(self) -> QtCore.QRect:
        screen = QtWidgets.QApplication.primaryScreen()
        return screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1920, 1080)

    def _clamp_window_position(self, desired: QtCore.QPoint) -> QtCore.QPoint:
        geo = self.frameGeometry()
        rect = self._available_screen_geometry()
        max_x = rect.left() + max(0, rect.width() - geo.width())
        max_y = rect.top() + max(0, rect.height() - geo.height())
        min_x = rect.left()
        min_y = rect.top()
        clamped_x = max(min_x, min(max_x, desired.x()))
        clamped_y = max(min_y, min(max_y, desired.y()))
        return QtCore.QPoint(clamped_x, clamped_y)

    # --- Bubble interactions --------------------------------------------
    def _begin_bubble_transform(self, pos: QtCore.QPointF) -> bool:
        bubble = getattr(self, "_bubble", None)
        if not bubble:
            return False
        handle = self._bubble_handle_rect()
        return bubble.begin_transform(self, pos, handle)

    def _update_bubble_transform(self, pos: QtCore.QPointF) -> bool:
        bubble = getattr(self, "_bubble", None)
        if not bubble:
            return False
        return bubble.update_transform(self, pos)

    def _update_bubble_cursor(self, pos: QtCore.QPointF | None):
        bubble = getattr(self, "_bubble", None)
        if not bubble:
            return
        handle = self._bubble_handle_rect()
        bubble.update_cursor(self, pos, handle)

    def _end_bubble_transform(self) -> bool:
        bubble = getattr(self, "_bubble", None)
        if not bubble:
            return False
        return bubble.end_transform(self)

    def _compute_panel_size_hint(self) -> tuple[float, float]:
        bubble = getattr(self, "_bubble", None)
        default_w = 360.0
        default_h = 110.0
        if not bubble:
            return (default_w, default_h)
        width_hint = getattr(bubble, "width_hint", default_w) or default_w
        height_hint = getattr(bubble, "height_hint", default_h) or default_h
        return (float(width_hint), float(height_hint))

    # --- Layout helpers -------------------------------------------------
    def _apply_window_preferred_size(self):
        sprite_w = max(120.0, float(self._sprite_size.width()))
        sprite_h = max(120.0, float(self._sprite_size.height()))
        panel_w_hint, panel_h_hint = self._compute_panel_size_hint()
        bubble = getattr(self, "_bubble", None)
        if bubble:
            bubble.width_hint = panel_w_hint
            bubble.height_hint = panel_h_hint

        desired_w = max(
            380,
            int(round(max(sprite_w + 120.0, panel_w_hint + 48.0))),
        )
        desired_h = max(
            320,
            int(round(sprite_h + panel_h_hint + 120.0)),
        )
        current_size = self.size()
        min_size = self.minimumSize()
        min_changed = (
            min_size.width() != desired_w or min_size.height() != desired_h
        )
        needs_resize = (
            current_size.width() < desired_w or current_size.height() < desired_h
        )

        if min_changed or needs_resize:
            self._sizing_in_progress = True
            try:
                if min_changed:
                    self.setMinimumSize(desired_w, desired_h)
                if needs_resize:
                    self.resize(
                        max(current_size.width(), desired_w),
                        max(current_size.height(), desired_h),
                    )
            finally:
                self._sizing_in_progress = False
        self.update()

    def _update_sprite_size_hint(self, movie: QtGui.QMovie | None):
        if movie and movie.isValid():
            rect = movie.frameRect()
            if rect.width() > 0 and rect.height() > 0:
                self._sprite_size = rect.size()
                self._apply_window_preferred_size()
                return
        self._sprite_size = QtCore.QSize(200, 200)
        self._apply_window_preferred_size()

    # --- Rendering helpers ----------------------------------------------
    def _draw_text_panel(self, p: QtGui.QPainter, bubble, alpha: int):
        text = (bubble.text or "").strip()
        if not text or alpha <= 0:
            bubble.panel_rect = None
            return
        scale = max(0.4, min(2.5, float(getattr(bubble, "scale", 1.0))))
        offset = bubble.offset if isinstance(bubble.offset, QtCore.QPointF) else QtCore.QPointF(0.0, 0.0)

        target_width = max(160.0, float(self._sprite_size.width()))
        base_panel_width = max(
            80.0,
            min(target_width, float(self.width()) - 24.0),
        )
        panel_width = max(80.0, min(float(self.width()) - 24.0, base_panel_width * scale))

        inner_padding_x = 28.0
        inner_padding_y = 22.0
        font = QtGui.QFont()
        font.setPointSizeF(12.0)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        metrics = QtGui.QFontMetrics(font)
        text_flags = int(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignTop
        )
        text_flags |= int(QtCore.Qt.TextFlag.TextWordWrap)
        available_text_width = max(60.0, panel_width - inner_padding_x * 2.0)
        text_metrics = metrics.boundingRect(
            QtCore.QRect(0, 0, int(round(available_text_width)), 4000),
            text_flags,
            text,
        )
        text_height = max(float(metrics.lineSpacing()), float(text_metrics.height()))
        panel_height = max(bubble.height_hint, text_height + inner_padding_y * 2.0)
        adjusted_panel_height = panel_height

        sprite_center = self._sprite_center()
        sprite_half_h = float(max(20.0, self._sprite_size.height() / 2.0))
        gap = 28.0
        margin_top = 18.0
        margin_bottom = 24.0

        below_top = sprite_center.y() + sprite_half_h + gap
        available_below = self.height() - margin_bottom - below_top
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
            adjusted_panel_height = min(panel_height, self.height() - margin_top - margin_bottom)

        if place_below:
            top = max(margin_top, below_top)
            if top + adjusted_panel_height + margin_bottom > self.height():
                adjusted_panel_height = max(0.0, self.height() - margin_bottom - top)
            bubble.side = "below"
        else:
            bottom_edge = min(above_bottom, self.height() - margin_bottom)
            top = max(margin_top, bottom_edge - adjusted_panel_height)
            bubble.side = "above"

        top += offset.y()
        max_top = self.height() - margin_bottom - adjusted_panel_height
        top = max(margin_top, min(max_top, top))

        if adjusted_panel_height <= 0.0:
            bubble.panel_rect = None
            return

        left = sprite_center.x() - panel_width / 2.0 + offset.x()
        min_left = 12.0
        max_left = self.width() - panel_width - 12.0
        if max_left < min_left:
            min_left = max_left = max(self.width() - panel_width, 0.0)
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

        drop_shadow = QtWidgets.QGraphicsDropShadowEffect()
        drop_shadow.setBlurRadius(32)
        drop_shadow.setOffset(0.0, 6.0)
        drop_shadow.setColor(QtGui.QColor(4, 7, 20, int(base_alpha * 0.45)))

        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        p.setBrush(QtGui.QBrush(QtGui.QColor(4, 7, 20, int(base_alpha * 0.35))))
        p.drawRoundedRect(shadow_rect, corner_radius + 8.0, corner_radius + 8.0)

        p.setPen(QtGui.QPen(outline_gradient, 1.8))
        p.setBrush(QtGui.QBrush(fill_gradient))
        p.drawRoundedRect(panel_rect, corner_radius, corner_radius)

        p.save()
        p.setClipPath(sheen_clip)
        p.setBrush(QtGui.QBrush(sheen_gradient))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRect(panel_rect)
        p.restore()

        text_pen = QtGui.QPen(QtGui.QColor("#0f172a"))
        text_pen.setWidthF(1.2)
        text_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(text_pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawText(text_rect, text, text_option)

        bubble.panel_rect = QtCore.QRectF(panel_rect)
        p.restore()

    def _apply_card_shadow(
        self,
        widget: QtWidgets.QWidget,
        *,
        blur_radius: float = 28.0,
        y_offset: float = 10.0,
        opacity: int = 150,
    ):
        shadow = QtWidgets.QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur_radius)
        shadow.setOffset(0.0, y_offset)
        shadow.setColor(QtGui.QColor(4, 7, 20, opacity))
        widget.setGraphicsEffect(shadow)

    # --- GIF helpers ----------------------------------------------------
    def _load_gif(self, path: str | None):
        if self._gif_movie:
            try:
                self._gif_movie.frameChanged.disconnect(self._on_movie_frame_changed)
            except (RuntimeError, TypeError):
                pass
            self._gif_movie.stop()
            self._gif_movie = None
        self._paint_debug_logged = False
        self._movie_debug_logged = False

        if not path:
            _debug(self, "No GIF path provided; using fallback drawing")
            self._update_sprite_size_hint(None)
            return

        path_obj = Path(path)
        if not path_obj.is_file():
            _debug(self, f"GIF path missing: {path}")
            self._update_sprite_size_hint(None)
            return

        movie = QtGui.QMovie(str(path_obj))
        if not movie.isValid():
            _debug(self, f"Failed to load GIF (invalid): {path}")
            QtWidgets.QMessageBox.warning(
                self,
                "GIF Load Error",
                f"Failed to load animation. The file may be corrupt or in an unsupported format.\n\nFile: {path}",
            )
            self._update_sprite_size_hint(None)
            return

        _debug(self, f"Loaded GIF: {path}")
        movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(self._on_movie_frame_changed)
        self._gif_movie = movie
        if not movie.jumpToFrame(0):
            _debug(self, "jumpToFrame(0) failed; will rely on playback frames")
        movie.start()
        self._update_sprite_size_hint(movie)

    def _on_movie_frame_changed(self, _frame: int):
        if self._gif_movie:
            pixmap = self._gif_movie.currentPixmap()
            if not pixmap.isNull():
                frame_size = pixmap.size()
                if not getattr(self, "_movie_debug_logged", False):
                    self._movie_debug_logged = True
                    _debug(
                        self,
                        f"GIF frame ready: size={frame_size.width()}x{frame_size.height()} alpha={pixmap.hasAlphaChannel()}",
                    )
                if frame_size != self._sprite_size:
                    self._sprite_size = QtCore.QSize(frame_size)
                    self._apply_window_preferred_size()
        self.update()

    def _save_debug_image(self, image: QtGui.QImage, filename: str):
        directory = Path(getattr(self, "_debug_capture_dir", Path.cwd()))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        target = directory / filename
        try:
            image.save(str(target))
            _debug(self, f"Saved debug image: {target}")
        except Exception:
            pass


__all__ = ["UIRenderMixin"]
