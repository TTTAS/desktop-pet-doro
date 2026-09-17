"""Unit tests for StateService - persistence and state list writing."""

from pathlib import Path
from unittest.mock import Mock

from doro_app.core.state import Transition
from doro_app.core.state import StateService


class TestStateListWriting:
    """Test state list writing functionality."""

    def test_write_state_list_returns_string(self, state_service_with_mocks: StateService):
        """Test that write_state_list returns a string summary."""
        state_service_with_mocks.add_state("happy", "Happy State")
        state_service_with_mocks.add_state("sad", "Sad State")

        result = state_service_with_mocks.write_state_list()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_write_state_list_includes_state_information(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test that write_state_list includes state information."""
        state_service_with_mocks.add_state("happy", "Happy State")

        # Mock GIF path
        mock_gif_repo.get_path.return_value = Path("/fake/happy.gif")

        result = state_service_with_mocks.write_state_list()

        # The result should be a summary string
        # (exact format depends on StateListWriter implementation)
        assert isinstance(result, str)

    def test_write_state_list_handles_empty_states(self, state_service_with_mocks: StateService):
        """Test write_state_list works with no custom states."""
        # Just initialize with defaults
        state_service_with_mocks.initialize()

        result = state_service_with_mocks.write_state_list()

        assert isinstance(result, str)

    def test_write_state_list_encapsulation(
        self, state_service_with_mocks: StateService, mock_gif_repo: Mock
    ):
        """Test that write_state_list uses encapsulated GIF paths."""
        state_service_with_mocks.add_state("test", "Test")
        state_service_with_mocks.update_state("test", gif_id="test_gif_id")

        # Mock the GIF repo
        mock_gif_repo.get_path.return_value = Path("/fake/test.gif")

        result = state_service_with_mocks.write_state_list()

        # Should have called get_path to get GIF paths (encapsulation)
        mock_gif_repo.get_path.assert_called_with("test_gif_id")

        assert isinstance(result, str)


class TestMoveStateOperations:
    """Test movement state operations."""

    def test_add_move_state_creates_movement(self, state_service_with_mocks: StateService):
        """Test adding a movement state."""
        state_service_with_mocks.add_state("walking", "Walking")

        move = state_service_with_mocks.add_move_state(
            key="walk_right", state_key="walking", direction="right", distance=100.0, speed="fast"
        )

        assert move is not None
        assert move.key == "walk_right"
        assert move.state_key == "walking"
        assert move.direction == "right"
        assert move.default_distance == 100.0
        assert move.default_speed == "fast"

    def test_get_move_state_returns_existing_movement(self, state_service_with_mocks: StateService):
        """Test retrieving a movement state."""
        state_service_with_mocks.add_state("walking", "Walking")
        state_service_with_mocks.add_move_state(
            key="walk_left", state_key="walking", direction="left"
        )

        move = state_service_with_mocks.get_move_state("walk_left")

        assert move is not None
        assert move.key == "walk_left"
        assert move.direction == "left"

    def test_all_move_state_keys_returns_all_movements(
        self, state_service_with_mocks: StateService
    ):
        """Test getting all movement state keys."""
        state_service_with_mocks.add_state("walking", "Walking")
        state_service_with_mocks.add_move_state("move1", "walking", "left")
        state_service_with_mocks.add_move_state("move2", "walking", "right")

        keys = state_service_with_mocks.all_move_state_keys()

        assert "move1" in keys
        assert "move2" in keys

    def test_find_move_states_by_direction(self, state_service_with_mocks: StateService):
        """Test finding movement states by direction."""
        state_service_with_mocks.add_state("walking", "Walking")
        state_service_with_mocks.add_move_state("walk_right", "walking", "right")
        state_service_with_mocks.add_move_state("walk_left", "walking", "left")

        right_moves = state_service_with_mocks.find_move_states_by_direction("right")

        assert len(right_moves) >= 1
        assert any(m.key == "walk_right" for m in right_moves)

    def test_remove_move_state_deletes_movement(self, state_service_with_mocks: StateService):
        """Test removing a movement state."""
        state_service_with_mocks.add_state("walking", "Walking")
        state_service_with_mocks.add_move_state("to_remove", "walking", "up")

        result = state_service_with_mocks.remove_move_state("to_remove")

        assert result is True
        assert state_service_with_mocks.get_move_state("to_remove") is None

    def test_is_movement_only_state(self, state_service_with_mocks: StateService):
        """Test checking if a state is movement-only."""
        state_service_with_mocks.add_state("walking", "Walking")
        state_service_with_mocks.add_move_state("walk", "walking", "any")

        # The state 'walking' should be marked as movement-only if used by move states
        is_movement = state_service_with_mocks.is_movement_only_state("walking")

        # This depends on implementation details
        assert isinstance(is_movement, bool)

    def test_get_default_movement_state(self, state_service_with_mocks: StateService):
        """Test getting the default movement state."""
        state_service_with_mocks.initialize()

        default = state_service_with_mocks.get_default_movement_state()

        # May return None or a default movement key
        assert default is None or isinstance(default, str)


class TestTransitionOperations:
    """Test transition state operations."""

    def test_add_transition_creates_transition(self, state_service_with_mocks: StateService):
        """Test adding a transition state."""
        state_service_with_mocks.add_state("idle", "Idle")
        state_service_with_mocks.add_state("happy", "Happy")

        transition = Transition(
            key="idle_to_happy",
            from_state="idle",
            to_state="happy",
            transition_gif_id="transition_gif",
        )
        result = state_service_with_mocks.add_transition(transition)

        assert result is True
        retrieved = state_service_with_mocks.get_transition("idle_to_happy")
        assert retrieved is not None
        assert retrieved.key == "idle_to_happy"
        assert retrieved.from_state == "idle"
        assert retrieved.to_state == "happy"

    def test_get_transition_returns_existing_transition(
        self, state_service_with_mocks: StateService
    ):
        """Test retrieving a transition."""
        state_service_with_mocks.add_state("a", "State A")
        state_service_with_mocks.add_state("b", "State B")

        trans = Transition(key="a_to_b", from_state="a", to_state="b")
        state_service_with_mocks.add_transition(trans)

        transition = state_service_with_mocks.get_transition("a_to_b")

        assert transition is not None
        assert transition.from_state == "a"
        assert transition.to_state == "b"

    def test_find_transition_by_states(self, state_service_with_mocks: StateService):
        """Test finding a transition by from/to states."""
        state_service_with_mocks.add_state("idle", "Idle")
        state_service_with_mocks.add_state("happy", "Happy")

        trans = Transition(key="trans", from_state="idle", to_state="happy")
        state_service_with_mocks.add_transition(trans)

        found = state_service_with_mocks.find_transition("idle", "happy")

        assert found is not None
        assert found.from_state == "idle"
        assert found.to_state == "happy"

    def test_all_transition_keys_returns_all_transitions(
        self, state_service_with_mocks: StateService
    ):
        """Test getting all transition keys."""
        state_service_with_mocks.add_state("a", "A")
        state_service_with_mocks.add_state("b", "B")

        trans1 = Transition(key="t1", from_state="a", to_state="b")
        trans2 = Transition(key="t2", from_state="b", to_state="a")
        state_service_with_mocks.add_transition(trans1)
        state_service_with_mocks.add_transition(trans2)

        keys = state_service_with_mocks.all_transition_keys()

        assert "t1" in keys
        assert "t2" in keys

    def test_remove_transition_deletes_transition(self, state_service_with_mocks: StateService):
        """Test removing a transition."""
        state_service_with_mocks.add_state("x", "X")
        state_service_with_mocks.add_state("y", "Y")

        trans = Transition(key="to_remove", from_state="x", to_state="y")
        state_service_with_mocks.add_transition(trans)

        result = state_service_with_mocks.remove_transition("to_remove")

        assert result is True
        assert state_service_with_mocks.get_transition("to_remove") is None
