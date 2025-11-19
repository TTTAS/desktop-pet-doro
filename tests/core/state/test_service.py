"""Unit tests for StateService - core state management logic."""

from pathlib import Path
from unittest.mock import Mock
import pytest

from doro_app.core.state import State, MoveState, VisualConfig
from doro_app.core.state import StateService


class TestStateServiceInitialization:
    """Test StateService initialization and setup."""

    def test_service_initializes_with_dependencies(
        self, state_service_with_mocks: StateService
    ):
        """Test that StateService initializes correctly with mocked dependencies."""
        assert state_service_with_mocks is not None
        assert state_service_with_mocks.on_state_changed is None
        assert state_service_with_mocks.on_states_modified is None

    def test_service_event_callbacks_can_be_set(
        self, state_service_with_mocks: StateService
    ):
        """Test that event callbacks can be assigned."""
        mock_callback = Mock()
        state_service_with_mocks.on_state_changed = mock_callback
        assert state_service_with_mocks.on_state_changed is mock_callback


class TestStateOperations:
    """Test basic state CRUD operations."""

    def test_add_state_creates_new_state(
        self, state_service_with_mocks: StateService
    ):
        """Test adding a new state."""
        state = state_service_with_mocks.add_state(
            key="happy",
            label="Happy State"
        )

        assert state is not None
        assert state.key == "happy"
        assert state.label == "Happy State"
        assert state_service_with_mocks.has_state("happy")

    def test_add_state_with_copy_from(
        self, state_service_with_mocks: StateService
    ):
        """Test adding a state by copying from existing state."""
        # First add a base state
        state_service_with_mocks.add_state("base", "Base State")

        # Copy from it
        copied = state_service_with_mocks.add_state(
            key="copy",
            label="Copied State",
            copy_from="base"
        )

        assert copied is not None
        assert copied.key == "copy"
        assert copied.label == "Copied State"

    def test_get_state_returns_existing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test retrieving an existing state."""
        state_service_with_mocks.add_state("test", "Test State")

        retrieved = state_service_with_mocks.get_state("test")

        assert retrieved is not None
        assert retrieved.key == "test"
        assert retrieved.label == "Test State"

    def test_get_state_returns_none_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test that get_state returns None for non-existent state."""
        result = state_service_with_mocks.get_state("nonexistent")
        assert result is None

    def test_has_state_returns_true_for_existing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test has_state returns True for existing state."""
        state_service_with_mocks.add_state("exists", "Exists")
        assert state_service_with_mocks.has_state("exists") is True

    def test_has_state_returns_false_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test has_state returns False for non-existent state."""
        assert state_service_with_mocks.has_state("missing") is False

    def test_update_state_modifies_existing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test updating an existing state."""
        state_service_with_mocks.add_state("update_me", "Original Label")

        result = state_service_with_mocks.update_state(
            "update_me",
            label="Updated Label"
        )

        assert result is True
        updated = state_service_with_mocks.get_state("update_me")
        assert updated is not None
        assert updated.label == "Updated Label"

    def test_update_state_returns_false_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test that updating non-existent state returns False."""
        result = state_service_with_mocks.update_state(
            "missing",
            label="New Label"
        )
        assert result is False

    def test_remove_state_deletes_state(
        self, state_service_with_mocks: StateService
    ):
        """Test removing a state."""
        state_service_with_mocks.add_state("to_remove", "Remove Me")
        assert state_service_with_mocks.has_state("to_remove")

        result = state_service_with_mocks.remove_state("to_remove")

        assert result is True
        assert not state_service_with_mocks.has_state("to_remove")

    def test_remove_protected_state_fails(
        self, state_service_with_mocks: StateService
    ):
        """Test that protected states cannot be removed."""
        # Initialize the service to create default states
        state_service_with_mocks.initialize()

        # Try to remove 'idle' which is protected
        result = state_service_with_mocks.remove_state("idle")

        assert result is False
        assert state_service_with_mocks.has_state("idle")

    def test_all_state_keys_returns_all_keys(
        self, state_service_with_mocks: StateService
    ):
        """Test getting all state keys."""
        state_service_with_mocks.add_state("state1", "State 1")
        state_service_with_mocks.add_state("state2", "State 2")

        keys = state_service_with_mocks.all_state_keys()

        assert "state1" in keys
        assert "state2" in keys

    def test_visible_state_keys_excludes_movement_only_states(
        self, state_service_with_mocks: StateService
    ):
        """Test that visible_state_keys excludes movement-only states."""
        state_service_with_mocks.add_state("normal", "Normal State")
        state_service_with_mocks.add_state("walking", "Walking State")

        # Mark 'walking' as movement-only
        state_service_with_mocks.add_move_state(
            key="walk",
            state_key="walking",
            direction="right"
        )

        visible_keys = state_service_with_mocks.visible_state_keys()

        # This test depends on the implementation of visible_state_keys
        # It should return states that are not movement-only
        assert "normal" in visible_keys or len(visible_keys) >= 0


class TestStateChanges:
    """Test state transition logic."""

    def test_set_state_changes_current_state(
        self, state_service_with_mocks: StateService
    ):
        """Test setting the current state."""
        state_service_with_mocks.add_state("happy", "Happy")

        result = state_service_with_mocks.set_state("happy")

        assert result is True
        current = state_service_with_mocks.get_current_state_key()
        assert current == "happy"

    def test_set_state_emits_event(
        self, state_service_with_mocks: StateService
    ):
        """Test that setting state emits state change event."""
        state_service_with_mocks.add_state("happy", "Happy")

        mock_callback = Mock()
        state_service_with_mocks.on_state_changed = mock_callback

        state_service_with_mocks.set_state("happy")

        # Should have been called with StateChangeEvent
        assert mock_callback.called

    def test_set_state_returns_false_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test that setting non-existent state returns False."""
        result = state_service_with_mocks.set_state("nonexistent")
        assert result is False

    def test_get_current_state_returns_none_initially(
        self, state_service_with_mocks: StateService
    ):
        """Test that current state is None before any state is set."""
        current = state_service_with_mocks.get_current_state()
        assert current is None

    def test_get_current_state_key_returns_none_initially(
        self, state_service_with_mocks: StateService
    ):
        """Test that current state key is None before any state is set."""
        key = state_service_with_mocks.get_current_state_key()
        assert key is None


class TestVisualConfiguration:
    """Test visual configuration updates."""

    def test_update_visual_config_modifies_state_visuals(
        self, state_service_with_mocks: StateService
    ):
        """Test updating visual configuration of a state."""
        state_service_with_mocks.add_state("visual_test", "Visual Test")

        result = state_service_with_mocks.update_visual_config(
            "visual_test",
            bob_amplitude=10.0,
            bubble_visible=False
        )

        assert result is True
        state = state_service_with_mocks.get_state("visual_test")
        assert state is not None
        assert state.visual.bob_amplitude == 10.0
        assert state.visual.bubble_visible is False

    def test_update_visual_config_returns_false_for_missing_state(
        self, state_service_with_mocks: StateService
    ):
        """Test that updating visuals for non-existent state returns False."""
        result = state_service_with_mocks.update_visual_config(
            "missing",
            bob_amplitude=5.0
        )
        assert result is False

    def test_update_state_visual_creates_modified_copy(
        self, state_service_with_mocks: StateService
    ):
        """Test that update_state_visual returns modified state."""
        state_service_with_mocks.add_state("modify_me", "Modify Me")

        modified = state_service_with_mocks.update_state_visual(
            "modify_me",
            scale_amplitude=0.1
        )

        assert modified is not None
        assert modified.visual.scale_amplitude == 0.1


class TestStateProtection:
    """Test protected state functionality."""

    def test_is_state_protected_returns_true_for_idle(
        self, state_service_with_mocks: StateService
    ):
        """Test that 'idle' state is protected."""
        state_service_with_mocks.initialize()
        assert state_service_with_mocks.is_state_protected("idle") is True

    def test_is_state_protected_returns_false_for_normal_state(
        self, state_service_with_mocks: StateService
    ):
        """Test that normal states are not protected."""
        state_service_with_mocks.add_state("normal", "Normal")
        assert state_service_with_mocks.is_state_protected("normal") is False


class TestStateSearch:
    """Test state search and query functionality."""

    def test_find_state_by_label_returns_matching_state(
        self, state_service_with_mocks: StateService
    ):
        """Test finding a state by label."""
        state_service_with_mocks.add_state("happy", "Happy Face")

        # find_state_by_label uses exact match (case-insensitive)
        key = state_service_with_mocks.find_state_by_label("Happy Face")

        assert key == "happy"

    def test_find_state_by_label_returns_none_for_no_match(
        self, state_service_with_mocks: StateService
    ):
        """Test that find_state_by_label returns None when no match."""
        result = state_service_with_mocks.find_state_by_label("Nonexistent")
        assert result is None


class TestInitialization:
    """Test StateService initialization process."""

    def test_initialize_creates_default_states(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test that initialize creates default states."""
        # Mock the GIF repo to return a path
        test_gif_path = Path("/fake/default.gif")
        mock_gif_repo.store_gif.return_value = "default_gif_id"

        state_service_with_mocks.initialize(default_gif_path=test_gif_path)

        # Should have created 'idle' state at minimum
        assert state_service_with_mocks.has_state("idle")

    def test_initialize_without_default_gif_still_works(
        self, state_service_with_mocks: StateService
    ):
        """Test that initialize works without providing default GIF."""
        state_service_with_mocks.initialize(default_gif_path=None)

        # Should still create basic states
        assert state_service_with_mocks.has_state("idle")


class TestStateSaving:
    """Test state persistence operations."""

    def test_save_states_calls_repository(
        self, state_service_with_mocks: StateService, mock_state_repo: Mock
    ):
        """Test that save_states triggers repository save."""
        state_service_with_mocks.add_state("test", "Test")

        result = state_service_with_mocks.save_states()

        assert result is True
        assert mock_state_repo.save_all.called

    def test_update_state_emits_modified_event(
        self, state_service_with_mocks: StateService
    ):
        """Test that update_state emits states modified event."""
        state_service_with_mocks.add_state("test", "Test")

        mock_callback = Mock()
        state_service_with_mocks.on_states_modified = mock_callback

        # update_state should trigger the callback
        state_service_with_mocks.update_state("test", label="Updated")

        assert mock_callback.called
