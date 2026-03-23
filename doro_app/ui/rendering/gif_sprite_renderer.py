"""GIF-based sprite renderer — wraps QMovie playback + fallback vector sprite."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from .fallback_sprite import draw_fallback_sprite

if TYPE_CHECKING:
    from ..viewmodels.doro_viewmodel import DoroViewModel

# Default size returned when no GIF is loaded (matches fallback sprite bounds)
_FALLBACK_SIZE = QtCore.QSize(180, 180)


class GifSpriteRenderer:
    """
    SpriteRenderer implementation backed by QMovie (GIF playback).

    When no movie is set the renderer draws a vector fallback sprite
    using visual parameters from the ViewModel.
    """

    def __init__(self, view_model: DoroViewModel) -> None:
        self._view_model = view_model
        self._movie: QtGui.QMovie | None = None

    @property
    def renderer_type(self) -> str:  # noqa: D401
        """Renderer type identifier."""
        return "gif"

    # ── Movie management (called by SpriteController) ──────────

    def set_movie(self, movie: QtGui.QMovie | None) -> None:
        """Replace the active QMovie (or clear it)."""
        self._movie = movie

    @property
    def movie(self) -> QtGui.QMovie | None:
        """Direct access to underlying QMovie (needed by SpriteController)."""
        return self._movie

    # ── SpriteRenderer protocol ────────────────────────────────

    def render(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        bob: float,
        scale: float,
    ) -> None:
        painter.save()
        painter.translate(center.x(), center.y() + bob)
        painter.scale(scale, scale)

        if self._movie and not self._movie.currentPixmap().isNull():
            pixmap = self._movie.currentPixmap()
            painter.translate(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            painter.drawPixmap(0, 0, pixmap)
        else:
            draw_fallback_sprite(
                painter,
                self._view_model.fill_colors,
                self._view_model.cheek_alpha,
                self._view_model.blush_color,
                self._view_model.eye_color,
            )

        painter.restore()

    def current_size(self) -> QtCore.QSize:
        if self._movie:
            rect = self._movie.frameRect()
            if rect.isValid():
                return rect.size()
        return _FALLBACK_SIZE

    def is_valid(self) -> bool:
        return (
            self._movie is not None
            and self._movie.isValid()
            and not self._movie.currentPixmap().isNull()
        )

    def current_pixmap(self) -> QtGui.QPixmap | None:
        if self._movie and self._movie.isValid():
            pix = self._movie.currentPixmap()
            if not pix.isNull():
                return pix
        return None
