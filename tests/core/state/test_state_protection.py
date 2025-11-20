"""Unit tests for StateService - state transition protection mechanism.

These tests verify that the state protection mechanism works correctly:
- Rejecting state changes during transitions
- Accepting changes after transitions complete
- Allowing forced state changes with force=True
- Ensuring rejected requests don't fire events

This is a TDD approach: tests are written first, then the implementation follows.
"""

from unittest.mock import Mock
import pytest

from doro_app.core.state import StateService, StateChangeEvent


class TestTransitionProtection:
    """Test state transition protection mechanism."""

    def test_reject_state_change_during_transition(
        self, state_service_with_mocks: StateService
    ):
        """When transitioning, new set_state requests should be rejected.

        Scenario:
            1. Start in idle state
            2. Begin transition (set _is_transitioning = True)
            3. Attempt to change to happy state
            4. Request should be rejected
            5. Current state should remain idle
        """
        # Arrange - Set up states
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.add_state("sad", "Sad")
        service.set_state("idle")

        # Simulate transition in progress
        service._is_transitioning = True

        # Act - Try to change state during transition
        result = service.set_state("happy")

        # Assert
        assert result is False, "State change should be rejected during transition"
        current = service.get_current_state()
        assert current.key == "idle", "Current state should not change"

    def test_accept_state_change_after_transition_completes(
        self, state_service_with_mocks: StateService
    ):
        """After transition completes, new requests should be accepted.

        Scenario:
            1. Start in idle state
            2. Begin transition (_is_transitioning = True)
            3. Complete transition (_is_transitioning = False)
            4. Attempt to change to happy state
            5. Request should succeed
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")

        # Simulate transition lifecycle
        service._is_transitioning = True
        service._is_transitioning = False

        # Act - Try to change state after transition completes
        result = service.set_state("happy")

        # Assert
        assert result is True, "State change should succeed after transition completes"
        current = service.get_current_state()
        assert current.key == "happy", "State should have changed to happy"

    def test_force_flag_bypasses_transition_protection(
        self, state_service_with_mocks: StateService
    ):
        """force=True should bypass transition protection.

        Scenario:
            Used by MovementManager to ensure movement states can override
            transitions without being blocked.

        Steps:
            1. Start in idle state
            2. Begin transition (_is_transitioning = True)
            3. Call set_state("walking", force=True)
            4. Request should succeed despite ongoing transition
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("walking", "Walking")
        service.set_state("idle")

        # Simulate transition in progress
        service._is_transitioning = True

        # Act - Force state change
        result = service.set_state("walking", force=True)

        # Assert
        assert result is True, "force=True should bypass protection"
        current = service.get_current_state()
        assert current.key == "walking", "State should have changed to walking"

    def test_rejected_request_does_not_fire_event(
        self, state_service_with_mocks: StateService
    ):
        """Rejected state change requests should not trigger on_state_changed event.

        Scenario:
            1. Register event callback
            2. Begin transition
            3. Attempt state change (will be rejected)
            4. Callback should NOT be invoked
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")

        # Register callback
        mock_callback = Mock()
        service.on_state_changed = mock_callback

        # Simulate transition in progress
        service._is_transitioning = True

        # Act - Try to change state (will be rejected)
        result = service.set_state("happy")

        # Assert
        assert result is False, "Request should be rejected"
        mock_callback.assert_not_called()

    def test_successful_request_fires_event(
        self, state_service_with_mocks: StateService
    ):
        """Successful state change should trigger on_state_changed event.

        This is a sanity check to ensure events still work correctly
        when protection is not active.
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")

        # Register callback
        mock_callback = Mock()
        service.on_state_changed = mock_callback

        # Ensure no transition in progress
        service._is_transitioning = False

        # Act - Change state normally
        result = service.set_state("happy")

        # Assert
        assert result is True, "Request should succeed"
        mock_callback.assert_called_once()

        # Verify event details
        call_args = mock_callback.call_args[0]
        event = call_args[0]
        assert isinstance(event, StateChangeEvent)
        assert event.old_key == "idle"
        assert event.new_key == "happy"

    def test_initial_state_has_no_transition_lock(
        self, state_service_with_mocks: StateService
    ):
        """After initialization, _is_transitioning should be False.

        Ensures the service starts in a ready state.
        """
        # Arrange & Act
        service = state_service_with_mocks

        # Assert
        assert hasattr(service, "_is_transitioning"), "Service should have _is_transitioning attribute"
        assert service._is_transitioning is False, "Initially should not be transitioning"

    def test_multiple_rejected_requests_remain_rejected(
        self, state_service_with_mocks: StateService
    ):
        """Multiple requests during transition should all be rejected.

        Scenario: User rapidly clicks state menu while transition is playing.
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("state1", "State 1")
        service.add_state("state2", "State 2")
        service.add_state("state3", "State 3")
        service.set_state("idle")

        # Simulate transition in progress
        service._is_transitioning = True

        # Act - Rapid state change attempts
        result1 = service.set_state("state1")
        result2 = service.set_state("state2")
        result3 = service.set_state("state3")

        # Assert - All rejected
        assert result1 is False, "First request should be rejected"
        assert result2 is False, "Second request should be rejected"
        assert result3 is False, "Third request should be rejected"

        # State should not have changed
        current = service.get_current_state()
        assert current.key == "idle", "State should remain idle"


class TestTransitionProtectionEdgeCases:
    """Test edge cases and error conditions."""

    def test_force_change_to_nonexistent_state_still_fails(
        self, state_service_with_mocks: StateService
    ):
        """force=True should not allow changing to non-existent states.

        The force flag bypasses transition protection, but not validation.
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.set_state("idle")
        service._is_transitioning = True

        # Act - Force change to non-existent state
        result = service.set_state("does_not_exist", force=True)

        # Assert
        assert result is False, "Should fail due to non-existent state"
        current = service.get_current_state()
        assert current.key == "idle", "State should remain idle"

    def test_state_change_to_same_state_during_transition(
        self, state_service_with_mocks: StateService
    ):
        """Attempting to change to current state during transition.

        Should be rejected (same protection rules apply).
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.set_state("idle")
        service._is_transitioning = True

        # Act - Try to "change" to same state
        result = service.set_state("idle")

        # Assert
        assert result is False, "Should be rejected even for same state"

    def test_force_change_to_same_state_succeeds(
        self, state_service_with_mocks: StateService
    ):
        """force=True changing to same state should succeed.

        This might be used to reset/refresh a state.
        """
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.set_state("idle")
        service._is_transitioning = True

        # Act
        result = service.set_state("idle", force=True)

        # Assert
        assert result is True, "Force change to same state should succeed"


class TestTransitionProtectionWithCallbacks:
    """Test interaction between protection mechanism and callbacks."""

    def test_callback_receives_correct_old_key_after_forced_change(
        self, state_service_with_mocks: StateService
    ):
        """Forced changes should still provide correct old_key in event."""
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("walking", "Walking")
        service.set_state("idle")

        mock_callback = Mock()
        service.on_state_changed = mock_callback

        service._is_transitioning = True

        # Act
        service.set_state("walking", force=True)

        # Assert
        mock_callback.assert_called_once()
        event = mock_callback.call_args[0][0]
        assert event.old_key == "idle"
        assert event.new_key == "walking"

    def test_no_callback_during_rejected_rapid_changes(
        self, state_service_with_mocks: StateService
    ):
        """No callbacks should fire for any rejected requests."""
        # Arrange
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("state1", "State 1")
        service.add_state("state2", "State 2")
        service.set_state("idle")

        mock_callback = Mock()
        service.on_state_changed = mock_callback
        service._is_transitioning = True

        # Act - Rapid requests
        service.set_state("state1")
        service.set_state("state2")
        service.set_state("state1")

        # Assert - No callbacks at all
        mock_callback.assert_not_called()
