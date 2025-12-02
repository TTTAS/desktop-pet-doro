"""Tests for TransitionCoordinator."""

import pytest
from unittest.mock import Mock

from doro_app.core.state.transition_coordinator import TransitionCoordinator
from doro_app.core.state.models import TransitionState


class TestTransitionCoordinatorFinding:
    """Tests for finding transitions."""

    def test_find_transition_exists(self):
        """Can find transition between states."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        transition = TransitionState(
            key="idle_to_happy",
            from_state="idle",
            to_state="happy",
            transition_gif_id="trans_123"
        )
        coordinator.add(transition)

        # Act
        result = coordinator.find("idle", "happy")

        # Assert
        assert result is not None
        assert result.key == "idle_to_happy"

    def test_find_transition_not_found(self):
        """Returns None when transition not found."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.find("idle", "happy")

        # Assert
        assert result is None

    def test_get_by_key_exists(self):
        """Can get transition by key."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        transition = TransitionState(
            key="idle_to_happy",
            from_state="idle",
            to_state="happy",
            transition_gif_id="trans_123"
        )
        coordinator.add(transition)

        # Act
        result = coordinator.get("idle_to_happy")

        # Assert
        assert result is not None
        assert result.from_state == "idle"

    def test_get_by_key_not_found(self):
        """Returns None when key not found."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.get("nonexistent")

        # Assert
        assert result is None

    def test_all_keys_empty(self):
        """Returns empty list when no transitions."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.all_keys()

        # Assert
        assert result == []

    def test_all_keys_with_transitions(self):
        """Returns all transition keys."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        coordinator.add(TransitionState("trans1", "a", "b", "gif1"))
        coordinator.add(TransitionState("trans2", "b", "c", "gif2"))

        # Act
        result = coordinator.all_keys()

        # Assert
        assert len(result) == 2
        assert "trans1" in result
        assert "trans2" in result


class TestTransitionCoordinatorLocking:
    """Tests for transition lock management."""

    def test_begin_acquires_lock(self):
        """Can acquire transition lock."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.begin()

        # Assert
        assert result is True
        assert coordinator.is_active() is True

    def test_begin_fails_when_locked(self):
        """Cannot acquire lock when already locked."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        coordinator.begin()

        # Act
        result = coordinator.begin()

        # Assert
        assert result is False
        assert coordinator.is_active() is True

    def test_end_releases_lock(self):
        """Can release transition lock."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        coordinator.begin()

        # Act
        result = coordinator.end()

        # Assert
        assert result is True
        assert coordinator.is_active() is False

    def test_end_fails_when_not_locked(self):
        """Cannot release lock when not locked."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.end()

        # Assert
        assert result is False

    def test_is_active_initially_false(self):
        """Lock is inactive initially."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act & Assert
        assert coordinator.is_active() is False


class TestTransitionCoordinatorRepository:
    """Tests for repository operations."""

    def test_load_from_repo_no_repo(self):
        """Can handle no repository gracefully."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act (should not crash)
        coordinator.load_from_repo()

        # Assert
        assert coordinator.all_keys() == []

    def test_load_from_repo_with_data(self):
        """Can load transitions from repository."""
        # Arrange
        repo = Mock()
        trans1 = TransitionState("t1", "a", "b", "gif1")
        trans2 = TransitionState("t2", "b", "c", "gif2")
        repo.load_all.return_value = {"t1": trans1, "t2": trans2}
        coordinator = TransitionCoordinator(transition_repo=repo)

        # Act
        coordinator.load_from_repo()

        # Assert
        assert len(coordinator.all_keys()) == 2
        assert coordinator.get("t1") is not None
        assert coordinator.get("t2") is not None


class TestTransitionCoordinatorModification:
    """Tests for adding/removing transitions."""

    def test_add_transition(self):
        """Can add a transition."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        transition = TransitionState("t1", "a", "b", "gif1")

        # Act
        coordinator.add(transition)

        # Assert
        assert coordinator.get("t1") is not None

    def test_remove_transition_exists(self):
        """Can remove an existing transition."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)
        transition = TransitionState("t1", "a", "b", "gif1")
        coordinator.add(transition)

        # Act
        result = coordinator.remove("t1")

        # Assert
        assert result is True
        assert coordinator.get("t1") is None

    def test_remove_transition_not_found(self):
        """Returns False when removing non-existent transition."""
        # Arrange
        coordinator = TransitionCoordinator(transition_repo=None)

        # Act
        result = coordinator.remove("nonexistent")

        # Assert
        assert result is False


class TestTransitionCoordinatorInitialization:
    """Tests for initialization."""

    def test_init_with_repo(self):
        """Can initialize with repository."""
        # Arrange
        repo = Mock()

        # Act
        coordinator = TransitionCoordinator(transition_repo=repo)

        # Assert
        assert coordinator._transition_repo is repo
        assert coordinator.is_active() is False

    def test_init_without_repo(self):
        """Can initialize without repository."""
        # Arrange & Act
        coordinator = TransitionCoordinator(transition_repo=None)

        # Assert
        assert coordinator._transition_repo is None
        assert coordinator.is_active() is False
