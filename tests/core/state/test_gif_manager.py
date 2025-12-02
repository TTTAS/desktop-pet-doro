"""Tests for GifManager."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from doro_app.core.state.gif_manager import GifManager
from doro_app.core.exceptions import GifNotFoundError, GifStorageError


class TestGifManagerPathOperations:
    """Tests for GIF path retrieval operations."""

    def test_get_path_by_id_success(self, tmp_path):
        """Can get GIF path by resource ID."""
        # Arrange
        gif_repo = Mock()
        gif_path = tmp_path / "test.gif"
        gif_repo.get_path.return_value = gif_path
        manager = GifManager(gif_repo)

        # Act
        result = manager.get_path_by_id("test-id")

        # Assert
        assert result == gif_path
        gif_repo.get_path.assert_called_once_with("test-id")

    def test_get_path_by_id_not_found(self):
        """Returns None when GIF not found."""
        # Arrange
        gif_repo = Mock()
        gif_repo.get_path.return_value = None
        manager = GifManager(gif_repo)

        # Act
        result = manager.get_path_by_id("nonexistent")

        # Assert
        assert result is None


class TestGifManagerStoreOperations:
    """Tests for GIF storage operations."""

    def test_store_success(self, tmp_path):
        """Can store a GIF successfully."""
        # Arrange
        gif_repo = Mock()
        gif_repo.store_gif.return_value = "new-gif-id"
        manager = GifManager(gif_repo)
        source = tmp_path / "source.gif"
        source.touch()

        # Act
        result = manager.store("source.gif", "idle")

        # Assert
        assert result == "new-gif-id"
        gif_repo.store_gif.assert_called_once_with("source.gif", "idle")

    def test_store_handles_not_found_error(self, tmp_path):
        """Handles GifNotFoundError gracefully."""
        # Arrange
        gif_repo = Mock()
        gif_repo.store_gif.side_effect = GifNotFoundError("Not found")
        manager = GifManager(gif_repo)

        # Act
        result = manager.store(Path("/nonexistent.gif"), "idle")

        # Assert
        assert result is None

    def test_store_handles_storage_error(self, tmp_path):
        """Handles GifStorageError gracefully."""
        # Arrange
        gif_repo = Mock()
        gif_repo.store_gif.side_effect = GifStorageError("Storage failed")
        manager = GifManager(gif_repo)
        source = tmp_path / "source.gif"

        # Act
        result = manager.store(source, "idle")

        # Assert
        assert result is None


class TestGifManagerDeleteOperations:
    """Tests for GIF deletion operations."""

    def test_delete_success(self):
        """Can delete a GIF successfully."""
        # Arrange
        gif_repo = Mock()
        gif_repo.delete.return_value = True
        manager = GifManager(gif_repo)

        # Act
        result = manager.delete("test-id")

        # Assert
        assert result is True
        gif_repo.delete.assert_called_once_with("test-id")

    def test_delete_failure(self):
        """Returns False when delete fails."""
        # Arrange
        gif_repo = Mock()
        gif_repo.delete.return_value = False
        manager = GifManager(gif_repo)

        # Act
        result = manager.delete("nonexistent")

        # Assert
        assert result is False


class TestGifManagerStoragePaths:
    """Tests for storage path queries."""

    def test_get_state_storage_path(self, tmp_path):
        """Can get state storage path."""
        # Arrange
        gif_repo = Mock()
        expected_path = tmp_path / "state_idle.gif"
        gif_repo.get_state_storage_path.return_value = expected_path
        manager = GifManager(gif_repo)

        # Act
        result = manager.get_state_storage_path("idle")

        # Assert
        assert result == expected_path
        gif_repo.get_state_storage_path.assert_called_once_with("idle")

    def test_get_move_storage_path(self, tmp_path):
        """Can get movement storage path."""
        # Arrange
        gif_repo = Mock()
        expected_path = tmp_path / "move_walking.gif"
        gif_repo.get_move_storage_path.return_value = expected_path
        manager = GifManager(gif_repo)

        # Act
        result = manager.get_move_storage_path("walking")

        # Assert
        assert result == expected_path
        gif_repo.get_move_storage_path.assert_called_once_with("walking")


class TestGifManagerInitialization:
    """Tests for GifManager initialization."""

    def test_init_with_repo(self):
        """Can initialize with repository."""
        # Arrange
        gif_repo = Mock()

        # Act
        manager = GifManager(gif_repo)

        # Assert
        assert manager._gif_repo is gif_repo
