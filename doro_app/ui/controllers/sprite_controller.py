"""Sprite controller — manages sprite loading and the active SpriteRenderer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from ...utils.logger import get_logger
from ..components.gif_player import GifPlayer
from ..rendering.gif_sprite_renderer import GifSpriteRenderer
from ..rendering.sprite_renderer import SpriteRenderer

if TYPE_CHECKING:
    from ..viewmodels.doro_viewmodel import DoroViewModel

logger = get_logger(__name__)


class SpriteController(QtCore.QObject):
    """
    Manages sprite loading and the active SpriteRenderer.

    Currently supports GIF sprites via GifSpriteRenderer.
    Future: Spine sprites via SpineSpriteRenderer.
    """

    # Signals
    sprite_renderer_changed = QtCore.Signal()  # renderer replaced or content updated
    sprite_size_changed = QtCore.Signal(QtCore.QSize)  # new_size
    frame_changed = QtCore.Signal(int)  # frame_number
    repaint_requested = QtCore.Signal()

    def __init__(self, view_model: DoroViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._gif_player = GifPlayer()
        self._gif_renderer = GifSpriteRenderer(view_model)
        self._renderers: dict[str, SpriteRenderer] = {
            "gif": self._gif_renderer,
        }
        self._renderer: SpriteRenderer = self._gif_renderer
        self._current_movie: QtGui.QMovie | None = None
        self._drag_movie: QtGui.QMovie | None = None

    @property
    def renderer(self) -> SpriteRenderer:
        """The active sprite renderer."""
        return self._renderer

    @property
    def renderer_type(self) -> str:
        """Shortcut — returns the active renderer's type identifier."""
        return self._renderer.renderer_type

    def register_renderer(self, renderer: SpriteRenderer) -> None:
        """Register an additional renderer (e.g. a future SpineSpriteRenderer)."""
        self._renderers[renderer.renderer_type] = renderer

    def switch_renderer(self, renderer_type: str) -> None:
        """Switch the active renderer by type identifier.

        Raises ``ValueError`` if *renderer_type* has not been registered.
        """
        if renderer_type not in self._renderers:
            available = ", ".join(sorted(self._renderers))
            raise ValueError(
                f"Unknown renderer type {renderer_type!r}. "
                f"Available: {available}"
            )
        if self._renderer.renderer_type == renderer_type:
            return
        # Clean up outgoing GIF movie signals to prevent phantom repaints
        if self._renderer.renderer_type == "gif" and self._current_movie:
            try:
                self._current_movie.frameChanged.disconnect(self._on_frame_changed)
            except (TypeError, RuntimeError):
                pass
        self._renderer = self._renderers[renderer_type]
        logger.info(f"Switched renderer to {renderer_type!r}")
        self.sprite_renderer_changed.emit()
        self.repaint_requested.emit()

    @property
    def gif_player(self) -> GifPlayer:
        """GifPlayer instance (needed by Window for resource cleanup)."""
        return self._gif_player

    def dispose_all(self) -> None:
        """Release resources for ALL renderers (call on application exit)."""
        self.end_drag_animation()
        for r in self._renderers.values():
            if hasattr(r, "dispose"):
                try:
                    r.dispose()
                except Exception:
                    logger.warning("Error disposing renderer %s", r.renderer_type, exc_info=True)

    def load_sprite(self, path: str | Path | None) -> bool:
        """
        Load a sprite from *path*.

        Currently only GIF files are supported.  The method resolves the
        file type and delegates to the appropriate renderer.
        """
        if not path:
            self._clear()
            return False

        path_obj = Path(path) if isinstance(path, str) else path
        if not path_obj.exists():
            logger.warning(f"Sprite file not found: {path}")
            self._clear()
            return False

        # Default: GIF
        return self._load_gif(path_obj)

    def set_movie_directly(self, movie: QtGui.QMovie, sprite_size: QtCore.QSize) -> None:
        """
        Set a QMovie directly (used by TransitionPlayer for transition GIFs).

        This bypasses the normal load path — the caller owns the movie lifetime.
        """
        self._gif_renderer.set_movie(movie)
        self._view_model.set_sprite_size(sprite_size)
        self.sprite_renderer_changed.emit()
        self.repaint_requested.emit()

    def start_drag_animation(self, path: Path) -> bool:
        """Play a temporary gesture sprite without changing persisted state."""
        if self._drag_movie is not None:
            return True
        movie = self._gif_player.load(path, size=self._view_model.sprite_size)
        if movie is None:
            return False
        self._drag_movie = movie
        movie.frameChanged.connect(self._on_drag_frame_changed)
        movie.finished.connect(movie.start)
        self._gif_renderer.set_temporary_movie(movie)
        self.repaint_requested.emit()
        return True

    def end_drag_animation(self) -> None:
        """Reveal the latest normal/transition sprite and release the drag movie."""
        movie, self._drag_movie = self._drag_movie, None
        if movie is None:
            return
        self._gif_renderer.set_temporary_movie(None)
        movie.frameChanged.disconnect(self._on_drag_frame_changed)
        movie.finished.disconnect(movie.start)
        self._gif_player.stop(movie)
        self.repaint_requested.emit()

    def _on_drag_frame_changed(self, _frame_number: int) -> None:
        self.repaint_requested.emit()

    # ── Private helpers ────────────────────────────────────────

    def tick(self, dt: float) -> None:
        """Advance the active renderer by *dt* seconds.

        Generic per-frame hook for time-based renderers. GIF playback is
        driven by QMovie and needs no manual advance, so this is a no-op for
        it; kept as a seam for future time-driven renderers.
        """
        update = getattr(self._renderer, "update", None)
        if callable(update):
            update(dt)

    def _load_gif(self, path: Path) -> bool:
        try:
            movie = self._gif_player.load(str(path))
            if not movie:
                logger.warning(f"Failed to load GIF: {path}")
                self._clear()
                return False

            # Disconnect old movie
            if self._current_movie:
                try:
                    self._current_movie.frameChanged.disconnect(self._on_frame_changed)
                except (TypeError, RuntimeError):
                    pass

            self._current_movie = movie
            movie.frameChanged.connect(self._on_frame_changed)

            # Ensure GIF renderer is active + update size
            self.switch_renderer("gif")
            self._gif_renderer.set_movie(movie)

            frame_rect = movie.frameRect()
            if frame_rect.isValid():
                frame_size = frame_rect.size()
                self._view_model.set_sprite_size(QtCore.QSize(frame_size))
                self.sprite_size_changed.emit(QtCore.QSize(frame_size))

            self.sprite_renderer_changed.emit()
            self.repaint_requested.emit()

            logger.debug(f"Loaded GIF sprite: {path}")
            return True

        except Exception as e:
            logger.error(f"Error loading sprite {path}: {e}")
            self._clear()
            return False

    def _clear(self) -> None:
        if self._current_movie:
            try:
                self._current_movie.frameChanged.disconnect(self._on_frame_changed)
            except (TypeError, RuntimeError):
                pass
            self._current_movie = None

        self._gif_renderer.set_movie(None)
        self.sprite_renderer_changed.emit()
        self.repaint_requested.emit()

    def _on_frame_changed(self, frame_number: int) -> None:
        if not self._current_movie:
            return

        self.frame_changed.emit(frame_number)
        self.repaint_requested.emit()
