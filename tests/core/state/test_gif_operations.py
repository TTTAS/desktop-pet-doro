"""Unit tests for StateService - GIF repository interactions."""

from pathlib import Path
from unittest.mock import Mock
import pytest

from doro_app.core.state import StateService


class TestGifOperations:
    """Test GIF-related operations through encapsulated API."""

    def test_get_gif_path_returns_path_for_state_with_gif(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test getting GIF path for a state that has a GIF."""
        # Setup: add state with GIF
        state_service_with_mocks.add_state("happy", "Happy")
        state_service_with_mocks.update_state("happy", gif_id="test_gif_123")

        # Mock gif_repo to return a path
        expected_path = Path("/fake/storage/test_gif_123.gif")
        mock_gif_repo.get_path.return_value = expected_path

        # Act
        result = state_service_with_mocks.get_gif_path("happy")

        # Assert
        assert result == expected_path
        mock_gif_repo.get_path.assert_called_with("test_gif_123")

    def test_get_gif_path_returns_none_for_state_without_gif(
        self, state_service_with_mocks: StateService
    ):
        """Test getting GIF path for a state without GIF returns None."""
        state_service_with_mocks.add_state("no_gif", "No GIF")

        result = state_service_with_mocks.get_gif_path("no_gif")

        assert result is None

    def test_get_gif_path_returns_none_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test getting GIF path for non-existent state returns None."""
        result = state_service_with_mocks.get_gif_path("nonexistent")
        assert result is None

    def test_get_gif_path_by_id_calls_repository(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test getting GIF path by resource ID."""
        expected_path = Path("/fake/storage/gif_456.gif")
        mock_gif_repo.get_path.return_value = expected_path

        result = state_service_with_mocks.get_gif_path_by_id("gif_456")

        assert result == expected_path
        mock_gif_repo.get_path.assert_called_with("gif_456")

    def test_store_gif_calls_repository_and_returns_id(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test storing a GIF file."""
        source_path = Path("/source/happy.gif")
        mock_gif_repo.store_gif.return_value = "new_gif_id_789"

        result = state_service_with_mocks.store_gif(source_path, "happy")

        assert result == "new_gif_id_789"
        mock_gif_repo.store_gif.assert_called_with(source_path, "happy")

    def test_delete_gif_calls_repository(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test deleting a GIF by ID."""
        mock_gif_repo.delete.return_value = True

        result = state_service_with_mocks.delete_gif("gif_to_delete")

        assert result is True
        mock_gif_repo.delete.assert_called_with("gif_to_delete")

    def test_get_state_storage_path_calls_repository(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test getting storage path for a state."""
        expected_path = Path("/fake/storage/STATE/happy")
        mock_gif_repo.get_state_storage_path.return_value = expected_path

        result = state_service_with_mocks.get_state_storage_path("happy")

        assert result == expected_path
        mock_gif_repo.get_state_storage_path.assert_called_with("happy")

    def test_get_move_storage_path_calls_repository(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test getting storage path for a movement."""
        expected_path = Path("/fake/storage/MOVE/walk_right")
        mock_gif_repo.get_move_storage_path.return_value = expected_path

        result = state_service_with_mocks.get_move_storage_path("walk_right")

        assert result == expected_path
        mock_gif_repo.get_move_storage_path.assert_called_with("walk_right")

    def test_sanitize_state_key_calls_repository(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test sanitizing a state key."""
        mock_gif_repo.sanitize_filename.return_value = "happy_state"

        result = state_service_with_mocks.sanitize_state_key("happy state")

        assert result == "happy_state"
        mock_gif_repo.sanitize_filename.assert_called_with("happy state")


class TestSetGifOperations:
    """Test set_gif and related operations."""

    def test_set_gif_stores_and_updates_state(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test set_gif stores GIF and updates state."""
        state_service_with_mocks.add_state("happy", "Happy")

        source_path = Path("/source/happy.gif")
        mock_gif_repo.store_gif.return_value = "stored_gif_id"

        result = state_service_with_mocks.set_gif("happy", source_path)

        assert result is True
        mock_gif_repo.store_gif.assert_called_with(source_path, "happy")

        # Verify state was updated with new gif_id
        state = state_service_with_mocks.get_state("happy")
        assert state is not None
        assert state.gif_id == "stored_gif_id"

    def test_set_gif_returns_false_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test set_gif returns False for non-existent state."""
        result = state_service_with_mocks.set_gif("missing", Path("/fake.gif"))
        assert result is False

    def test_get_gif_id_returns_id_for_state(
        self, state_service_with_mocks: StateService
    ):
        """Test getting GIF ID for a state."""
        state_service_with_mocks.add_state("test", "Test")
        state_service_with_mocks.update_state("test", gif_id="my_gif_123")

        gif_id = state_service_with_mocks.get_gif_id("test")

        assert gif_id == "my_gif_123"

    def test_get_gif_id_returns_none_for_state_without_gif(
        self, state_service_with_mocks: StateService
    ):
        """Test getting GIF ID for state without GIF returns None."""
        state_service_with_mocks.add_state("no_gif", "No GIF")

        gif_id = state_service_with_mocks.get_gif_id("no_gif")

        assert gif_id is None


class TestGifEncapsulation:
    """Test that GIF repository is properly encapsulated."""

    def test_gif_repo_is_not_directly_accessible(
        self, state_service_with_mocks: StateService
    ):
        """Test that _gif_repo is private and not exposed."""
        # Should not be able to access _gif_repo through public API
        # This is a design test - accessing private attributes is possible but discouraged
        assert hasattr(state_service_with_mocks, "_gif_repo")
        assert not hasattr(state_service_with_mocks, "gif_repo")

    def test_all_gif_operations_go_through_service_methods(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test that all GIF operations use service's encapsulated methods."""
        state_service_with_mocks.add_state("test", "Test")

        # All these should work without direct gif_repo access
        state_service_with_mocks.get_gif_path("test")
        state_service_with_mocks.get_gif_path_by_id("test_id")
        state_service_with_mocks.store_gif(Path("/test.gif"), "test")
        state_service_with_mocks.delete_gif("test_id")
        state_service_with_mocks.get_state_storage_path("test")
        state_service_with_mocks.get_move_storage_path("test_move")
        state_service_with_mocks.sanitize_state_key("test key")

        # Verify all methods were called on the mock
        assert mock_gif_repo.get_path.called
        assert mock_gif_repo.store_gif.called
        assert mock_gif_repo.delete.called
        assert mock_gif_repo.get_state_storage_path.called
        assert mock_gif_repo.get_move_storage_path.called
        assert mock_gif_repo.sanitize_filename.called
