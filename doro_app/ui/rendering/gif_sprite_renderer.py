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
        self._temporary_movie: QtGui.QMovie | None = None
        self._contact_bounds = QtCore.QRect()

    @property
    def renderer_type(self) -> str:
        """Renderer type identifier."""
        return "gif"

    # ── Movie management (called by SpriteController) ──────────

    def set_movie(self, movie: QtGui.QMovie | None) -> None:
        """Replace the active QMovie (or clear it)."""
        self._movie = movie
        # Freeze the contact rectangle at load time. Sampling each GIF frame
        # would make the desktop position jitter as paws/hair animate.
        self._contact_bounds = QtCore.QRect()
        if movie is not None:
            pixmap = movie.currentPixmap()
            if not pixmap.isNull():
                self._contact_bounds = QtGui.QRegion(pixmap.mask()).boundingRect()
                if self._contact_bounds.isEmpty():
                    self._contact_bounds = pixmap.rect()

    def contact_bounds(self) -> QtCore.QRect:
        """Stable visible bounds in sprite pixels, excluding transparent padding."""
        return QtCore.QRect(self._contact_bounds)

    @property
    def movie(self) -> QtGui.QMovie | None:
        """Direct access to underlying QMovie (needed by SpriteController)."""
        return self._temporary_movie if self._temporary_movie is not None else self._movie

    def set_temporary_movie(self, movie: QtGui.QMovie | None) -> None:
        """Show a gesture animation while retaining the latest state movie."""
        self._temporary_movie = movie

    def _is_movie_alive(self) -> bool:
        """Check if the underlying C++ QMovie object is still valid."""
        if self.movie is None:
            return False
        try:
            self.movie.state()  # lightweight C++ call
            return True
        except RuntimeError:
            # C++ object already deleted
            if self._temporary_movie is not None:
                self._temporary_movie = None
            else:
                self._movie = None
            return False

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

        if self._is_movie_alive() and not self.movie.currentPixmap().isNull():
            pixmap = self.movie.currentPixmap()
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
        if self._is_movie_alive():
            rect = self.movie.frameRect()
            if rect.isValid():
                return rect.size()
        return _FALLBACK_SIZE

    def is_valid(self) -> bool:
        return self._is_movie_alive() and not self.movie.currentPixmap().isNull()

    def current_pixmap(self) -> QtGui.QPixmap | None:
        if self._is_movie_alive() and self.movie.isValid():
            pix = self.movie.currentPixmap()
            if not pix.isNull():
                return pix
        return None
