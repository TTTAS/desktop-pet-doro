"""Tests for GifPlayer."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from doro_app.ui.components.gif_player import GifPlayer


class TestGifPlayer:
    """Tests for GifPlayer resource management."""

    def test_init(self):
        """Test GifPlayer initialization."""
        player = GifPlayer()
        assert player.count() == 0

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_load_valid_gif(self, mock_qmovie_class):
        """Test loading a valid GIF."""
        # Setup mock
        mock_movie = Mock()
        mock_movie.isValid.return_value = True
        mock_qmovie_class.return_value = mock_movie

        player = GifPlayer()
        result = player.load(Path("/fake/path.gif"))

        assert result is mock_movie
        assert player.count() == 1
        mock_movie.start.assert_called_once()

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_load_invalid_gif(self, mock_qmovie_class):
        """Test loading an invalid GIF."""
        # Setup mock
        mock_movie = Mock()
        mock_movie.isValid.return_value = False
        mock_qmovie_class.return_value = mock_movie

        player = GifPlayer()
        result = player.load(Path("/fake/invalid.gif"))

        assert result is None
        assert player.count() == 0
        mock_movie.start.assert_not_called()

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_load_with_size(self, mock_qmovie_class):
        """Test loading GIF with custom size."""
        from PySide6.QtCore import QSize

        mock_movie = Mock()
        mock_movie.isValid.return_value = True
        mock_qmovie_class.return_value = mock_movie

        player = GifPlayer()
        size = QSize(100, 100)
        player.load(Path("/fake/path.gif"), size=size)

        mock_movie.setScaledSize.assert_called_once_with(size)

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_clear(self, mock_qmovie_class):
        """Test clearing all movies."""
        mock_movie1 = Mock()
        mock_movie1.isValid.return_value = True
        mock_movie2 = Mock()
        mock_movie2.isValid.return_value = True

        mock_qmovie_class.side_effect = [mock_movie1, mock_movie2]

        player = GifPlayer()
        player.load(Path("/fake/1.gif"))
        player.load(Path("/fake/2.gif"))

        assert player.count() == 2

        player.clear()

        assert player.count() == 0
        mock_movie1.stop.assert_called_once()
        mock_movie1.deleteLater.assert_called_once()
        mock_movie2.stop.assert_called_once()
        mock_movie2.deleteLater.assert_called_once()

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_stop_specific_movie(self, mock_qmovie_class):
        """Test stopping a specific movie."""
        mock_movie1 = Mock()
        mock_movie1.isValid.return_value = True
        mock_movie2 = Mock()
        mock_movie2.isValid.return_value = True

        mock_qmovie_class.side_effect = [mock_movie1, mock_movie2]

        player = GifPlayer()
        movie1 = player.load(Path("/fake/1.gif"))
        player.load(Path("/fake/2.gif"))

        assert player.count() == 2

        result = player.stop(movie1)

        assert result is True
        assert player.count() == 1
        mock_movie1.stop.assert_called_once()
        mock_movie1.deleteLater.assert_called_once()

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_context_manager(self, mock_qmovie_class):
        """Test context manager auto-cleanup."""
        mock_movie = Mock()
        mock_movie.isValid.return_value = True
        mock_qmovie_class.return_value = mock_movie

        with GifPlayer() as player:
            player.load(Path("/fake/path.gif"))
            assert player.count() == 1

        # After exiting context, should be cleaned up
        mock_movie.stop.assert_called_once()
        mock_movie.deleteLater.assert_called_once()

    @patch('doro_app.ui.components.gif_player.QtGui.QMovie')
    def test_load_with_string_path(self, mock_qmovie_class):
        """Test loading GIF with string path."""
        mock_movie = Mock()
        mock_movie.isValid.return_value = True
        mock_qmovie_class.return_value = mock_movie

        player = GifPlayer()
        result = player.load("/fake/path.gif")

        assert result is mock_movie
        mock_qmovie_class.assert_called_once_with("/fake/path.gif")
