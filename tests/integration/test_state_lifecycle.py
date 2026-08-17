"""Integration tests for complete state lifecycle."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from doro_app.core.state import State, StateService, MoveState, Transition
from doro_app.core.state.repository import (
    StateRepository,
    MoveStateRepository,
    GifRepository,
    TransitionRepository,
)


@pytest.fixture
def temp_state_dir():
    """Create temporary directory for state storage."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def state_service(temp_state_dir):
    """Create StateService with temp repositories."""
    state_repo = StateRepository(temp_state_dir / "states.json")
    move_repo = MoveStateRepository(temp_state_dir / "move_states.json")
    gif_repo = GifRepository(temp_state_dir)
    transition_repo = TransitionRepository(temp_state_dir / "transitions.json")
    state_list_path = temp_state_dir / "state_list.txt"

    service = StateService(
        state_repo=state_repo,
        move_repo=move_repo,
        gif_repo=gif_repo,
        state_list_path=state_list_path,
        transition_repo=transition_repo,
        transition_gif_repo=GifRepository(temp_state_dir / "TRANSITION"),
    )

    # Initialize with default idle state
    service.initialize()

    return service


class TestStateLifecycle:
    """Integration tests for complete state lifecycle."""

    def test_create_state_and_retrieve(self, state_service):
        """Test creating a state and retrieving it."""
        # Create state
        state = state_service.add_state("happy", "Happy")
        assert state is not None
        assert state.key == "happy"
        assert state.label == "Happy"

        # Retrieve state
        retrieved = state_service.get_state("happy")
        assert retrieved is not None
        assert retrieved.key == "happy"
        assert retrieved.label == "Happy"

    def test_state_persistence(self, state_service):
        """Test that states persist across service instances."""
        temp_dir = state_service._state_repo.config_path.parent

        # Create state
        state_service.add_state("excited", "Excited")

        # Create new service instance
        new_repo = StateRepository(temp_dir / "states.json")
        new_move_repo = MoveStateRepository(temp_dir / "move_states.json")
        new_gif_repo = GifRepository(temp_dir)
        new_transition_repo = TransitionRepository(temp_dir / "transitions.json")
        new_service = StateService(
            state_repo=new_repo,
            move_repo=new_move_repo,
            gif_repo=new_gif_repo,
            state_list_path=temp_dir / "state_list.txt",
            transition_repo=new_transition_repo,
            transition_gif_repo=GifRepository(temp_dir / "TRANSITION"),
        )
        new_service.initialize()

        # State should still exist
        retrieved = new_service.get_state("excited")
        assert retrieved is not None
        assert retrieved.key == "excited"

    def test_state_change_events(self, state_service):
        """Test that state change events are emitted."""
        # Setup event listener
        events = []

        def on_state_changed(event):
            events.append(event)

        state_service.on_state_changed = on_state_changed

        # Create and switch to new state
        state_service.add_state("happy", "Happy")
        state_service.set_state("happy")

        # Should have received event
        assert len(events) == 1
        assert events[0].old_key == "idle"
        assert events[0].new_key == "happy"

    def test_protected_state_cannot_be_removed(self, state_service):
        """Test that protected states cannot be removed."""
        # Idle is protected by default
        result = state_service.remove_state("idle")
        assert result is False

        # Idle should still exist
        assert state_service.has_state("idle")

    def test_state_modification_events(self, state_service):
        """Test that modification events are emitted."""
        events = []

        def on_modified():
            events.append(True)

        state_service.on_states_modified = on_modified

        # Add state should trigger event
        state_service.add_state("happy", "Happy")
        assert len(events) == 1

        # Remove state should trigger event
        state_service.remove_state("happy")
        assert len(events) == 2


class TestMovementIntegration:
    """Integration tests for movement states."""

    def test_create_move_state_with_visual_state(self, state_service):
        """Test creating movement state linked to visual state."""
        # Note: 'walking' state is created by default in initialize()

        # Create movement state
        move_state = state_service.add_move_state(
            key="walk_left",
            state_key="walking",
            direction="left",
            speed="med",
        )

        assert move_state is not None
        assert move_state.state_key == "walking"

        # Retrieve movement state
        retrieved = state_service.get_move_state("walk_left")
        assert retrieved is not None
        assert retrieved.direction == "left"

    def test_find_move_states_by_direction(self, state_service):
        """Test finding movement states by direction."""
        # Note: 'walking' state is created by default in initialize()
        # Create movement states
        state_service.add_move_state("walk_left", "walking", "left")
        state_service.add_move_state("walk_right", "walking", "right")

        # Find left movements
        left_moves = state_service.find_move_states_by_direction("left")
        assert len(left_moves) > 0
        # Should include states with direction="left" and direction="any"
        # (Default walking state has direction="any")
        assert any(m.key == "walk_left" for m in left_moves)
        assert all("left" in m.direction or "any" in m.direction for m in left_moves)


class TestTransitionIntegration:
    """Integration tests for state transitions."""

    def test_create_transition_between_states(self, state_service):
        """Test creating transition between two states."""
        # Create states
        state_service.add_state("happy", "Happy")
        state_service.add_state("sad", "Sad")

        # Create transition
        transition = Transition(
            key="happy_to_sad",
            from_state="happy",
            to_state="sad",
        )
        result = state_service.add_transition(transition)
        assert result is True

        # Retrieve transition
        retrieved = state_service.find_transition("happy", "sad")
        assert retrieved is not None
        assert retrieved.from_state == "happy"
        assert retrieved.to_state == "sad"

    def test_transition_protection(self, state_service):
        """Test that state changes are blocked during transitions."""
        state_service.add_state("happy", "Happy")

        # Begin transition
        success = state_service.begin_transition()
        assert success is True
        assert state_service.is_transitioning() is True

        # State change should be rejected
        result = state_service.set_state("happy")
        assert result is False

        # End transition
        state_service.end_transition()
        assert state_service.is_transitioning() is False

        # State change should now succeed
        result = state_service.set_state("happy")
        assert result is True


class TestCompleteWorkflow:
    """Integration tests for complete workflows."""

    def test_full_state_customization_workflow(self, state_service):
        """Test complete workflow: create, modify, use, remove."""
        # Step 1: Create custom state
        state = state_service.add_state("excited", "Excited")
        assert state is not None

        # Step 2: Modify visual properties
        success = state_service.update_visual_config(
            "excited",
            bob_amplitude=10.0,
            scale_amplitude=0.08,
        )
        assert success is True

        # Step 3: Use the state
        success = state_service.set_state("excited")
        assert success is True
        assert state_service.get_current_state_key() == "excited"

        # Step 4: Remove the state (switch to idle first)
        state_service.set_state("idle")
        success = state_service.remove_state("excited")
        assert success is True
        assert not state_service.has_state("excited")
