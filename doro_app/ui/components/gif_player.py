"""GIF Player - unified QMovie resource management.

This module provides a safe, consistent way to manage QMovie objects
and prevent memory leaks.
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui
from typing_extensions import Self


class GifPlayer:
    """
    Unified GIF player with automatic resource cleanup.

    Manages QMovie lifecycle to prevent memory leaks and ensure
    proper cleanup when dialogs close or components are destroyed.

    Usage:
        # As context manager (recommended):
        with GifPlayer() as player:
            movie = player.load(path, size=QSize(96, 96))
            label.setMovie(movie)
        # Automatically cleaned up

        # Or manual management:
        player = GifPlayer()
        movie = player.load(path)
        label.setMovie(movie)
        # ... later
        player.clear()  # Must call manually
    """

    def __init__(self):
        """Initialize empty GIF player."""
        self._movies: list[QtGui.QMovie] = []

    def load(
        self,
        path: Path | str,
        size: QtCore.QSize | None = None,
        cache_mode: QtGui.QMovie.CacheMode = QtGui.QMovie.CacheMode.CacheAll,
    ) -> QtGui.QMovie | None:
        """
        Load and start playing a GIF.

        Args:
            path: Path to GIF file
            size: Optional size to scale to
            cache_mode: QMovie cache mode (default: CacheAll)

        Returns:
            QMovie object if successful, None if invalid
        """
        if isinstance(path, Path):
            path = str(path)

        movie = QtGui.QMovie(path)
        if not movie.isValid():
            return None

        movie.setCacheMode(cache_mode)

        if size:
            movie.setScaledSize(size)

        movie.start()
        self._movies.append(movie)
        return movie

    def stop(self, movie: QtGui.QMovie) -> bool:
        """
        Stop and remove a specific movie.

        Args:
            movie: QMovie to stop

        Returns:
            True if movie was found and removed
        """
        if movie in self._movies:
            movie.stop()
            # Detach from file immediately so the OS can release the handle.
            # deleteLater() alone is async and would keep the file locked
            # until the next event-loop iteration (causes WinError 32).
            movie.setFileName("")
            movie.deleteLater()
            self._movies.remove(movie)
            return True
        return False

    def clear(self) -> None:
        """Stop and clean up all movies."""
        for movie in self._movies:
            try:
                movie.stop()
                # Detach from file immediately so the OS can release the handle.
                # deleteLater() alone is async and would keep the file locked
                # until the next event-loop iteration (causes WinError 32).
                movie.setFileName("")
                movie.deleteLater()
            except RuntimeError:
                # Already deleted
                pass
        self._movies.clear()

    def count(self) -> int:
        """Get number of active movies."""
        return len(self._movies)

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - auto cleanup."""
        self.clear()

    def __del__(self):
        """Destructor - ensure cleanup."""
        self.clear()
