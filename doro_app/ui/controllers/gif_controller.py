"""GIF controller - handles GIF loading and playback."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from ...utils.logger import get_logger
from ..components.gif_player import GifPlayer

if TYPE_CHECKING:
    from ..viewmodels.doro_viewmodel import DoroViewModel

logger = get_logger(__name__)


class GifController(QtCore.QObject):
    """
    Manages GIF loading and playback.

    Responsibilities:
    - Load GIF files and create QMovie instances
    - Handle frame change events
    - Update sprite size based on GIF dimensions
    - Emit signals for UI updates
    """

    # Signals
    gif_loaded = QtCore.Signal(QtGui.QMovie)  # movie
    sprite_size_changed = QtCore.Signal(QtCore.QSize)  # new_size
    frame_changed = QtCore.Signal(int)  # frame_number
    repaint_requested = QtCore.Signal()

    def __init__(self, view_model: DoroViewModel):
        """
        Initialize GifController.

        Args:
            view_model: Presentation state ViewModel
        """
        super().__init__()
        self._view_model = view_model
        self._gif_player = GifPlayer()
        self._current_movie: QtGui.QMovie | None = None

    @property
    def current_movie(self) -> QtGui.QMovie | None:
        """Get currently loaded movie."""
        return self._current_movie

    def load_gif(self, path: str | Path | None) -> bool:
        """
        Load a GIF file.

        Args:
            path: Path to GIF file (None to clear)

        Returns:
            True if GIF was loaded successfully
        """
        if not path:
            self._clear_gif()
            return False

        path_obj = Path(path) if isinstance(path, str) else path
        if not path_obj.exists():
            logger.warning(f"GIF file not found: {path}")
            self._clear_gif()
            return False

        try:
            movie = self._gif_player.load(str(path_obj))
            if not movie:
                logger.warning(f"Failed to load GIF: {path}")
                self._clear_gif()
                return False

            # Disconnect old movie signals
            if self._current_movie:
                try:
                    self._current_movie.frameChanged.disconnect(self._on_frame_changed)
                except (TypeError, RuntimeError):
                    pass

            # Connect new movie signals
            self._current_movie = movie
            movie.frameChanged.connect(self._on_frame_changed)

            # Update sprite size based on GIF dimensions
            frame_rect = movie.frameRect()
            if frame_rect.isValid():
                frame_size = frame_rect.size()
                self._view_model.set_sprite_size(QtCore.QSize(frame_size))
                self.sprite_size_changed.emit(QtCore.QSize(frame_size))

            # Emit signals
            self.gif_loaded.emit(movie)
            self.repaint_requested.emit()

            logger.debug(f"Loaded GIF: {path}")
            return True

        except Exception as e:
            logger.error(f"Error loading GIF {path}: {e}")
            self._clear_gif()
            return False

    def _clear_gif(self) -> None:
        """Clear currently loaded GIF."""
        if self._current_movie:
            try:
                self._current_movie.frameChanged.disconnect(self._on_frame_changed)
            except (TypeError, RuntimeError):
                pass
            self._current_movie = None
            self.gif_loaded.emit(None)  # type: ignore
            self.repaint_requested.emit()

    def _on_frame_changed(self, frame_number: int) -> None:
        """
        Handle movie frame changes.

        Updates sprite size if frame dimensions change.
        """
        if not self._current_movie:
            return

        # Check if frame size changed
        frame_rect = self._current_movie.frameRect()
        if frame_rect.isValid():
            frame_size = frame_rect.size()
            current_size = self._view_model.sprite_size

            # Update sprite size if it changed
            if frame_size != current_size:
                self._view_model.set_sprite_size(QtCore.QSize(frame_size))
                self.sprite_size_changed.emit(QtCore.QSize(frame_size))

        self.frame_changed.emit(frame_number)
        self.repaint_requested.emit()
