"""PR B: request/commit state and transition-lock timeout.

These tests describe the intended behaviour before the implementation
lands. Existing set_state-during-lock tests stay valid: set_state still
returns False and does not emit while the lock is held. The new contract
is that the rejected key is remembered as requested_key and applied when
the lock is released or expires.
"""

from unittest.mock import Mock

from doro_app.core.state import StateService
from doro_app.core.state.transition_coordinator import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    TransitionCoordinator,
)


class FakeClock:
    """Monotonic clock the tests can step forward."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestLockTimeout:
    """Transition lock must not stay held forever."""

    def test_lock_expires_after_timeout(self):
        clock = FakeClock()
        coordinator = TransitionCoordinator(
            transition_repo=None,
            lock_timeout_seconds=5.0,
            clock=clock,
        )
        assert coordinator.begin() is True
        assert coordinator.is_active() is True

        clock.advance(4.9)
        assert coordinator.is_active() is True

        clock.advance(0.2)
        assert coordinator.is_active() is False

    def test_expire_if_needed_releases_and_reports(self):
        clock = FakeClock()
        coordinator = TransitionCoordinator(
            transition_repo=None,
            lock_timeout_seconds=1.0,
            clock=clock,
        )
        coordinator.begin()
        assert coordinator.expire_if_needed() is False

        clock.advance(1.0)
        assert coordinator.expire_if_needed() is True
        assert coordinator.is_active() is False
        assert coordinator.expire_if_needed() is False

    def test_begin_after_expiry_acquires_again(self):
        clock = FakeClock()
        coordinator = TransitionCoordinator(
            transition_repo=None,
            lock_timeout_seconds=1.0,
            clock=clock,
        )
        assert coordinator.begin() is True
        clock.advance(1.0)
        assert coordinator.begin() is True
        assert coordinator.is_active() is True

    def test_default_timeout_constant(self):
        assert DEFAULT_LOCK_TIMEOUT_SECONDS == 5.0


class TestRequestCommit:
    """requested_key vs committed_key on StateService."""

    def test_request_without_lock_commits_immediately(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")

        assert service.request_state("happy") is True
        assert service.get_committed_state_key() == "happy"
        assert service.get_requested_state_key() == "happy"
        assert service.get_current_state_key() == "happy"

    def test_request_during_lock_is_queued_not_committed(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.add_state("sad", "Sad")
        service.set_state("idle")
        service.begin_transition()

        assert service.request_state("happy") is False
        assert service.get_committed_state_key() == "idle"
        assert service.get_requested_state_key() == "happy"
        assert service.get_current_state_key() == "idle"

        assert service.request_state("sad") is False
        assert service.get_requested_state_key() == "sad"
        assert service.get_committed_state_key() == "idle"

    def test_end_transition_commits_last_request(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.add_state("sad", "Sad")
        service.set_state("idle")

        callback = Mock()
        service.on_state_changed = callback
        service.begin_transition()
        service.request_state("happy")
        service.request_state("sad")
        callback.reset_mock()

        assert service.end_transition() is True
        assert service.get_committed_state_key() == "sad"
        assert service.get_requested_state_key() == "sad"
        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.old_key == "idle"
        assert event.new_key == "sad"

    def test_set_state_is_thin_wrapper_for_request(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")
        service.begin_transition()

        assert service.set_state("happy") is False
        assert service.get_requested_state_key() == "happy"
        assert service.get_committed_state_key() == "idle"

    def test_force_commits_and_replaces_pending_request(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.add_state("walking", "Walking")
        service.set_state("idle")
        service.begin_transition()
        service.request_state("happy")

        assert service.set_state("walking", force=True) is True
        assert service.get_committed_state_key() == "walking"
        assert service.get_requested_state_key() == "walking"
        assert service.is_transitioning() is True

        assert service.end_transition() is True
        assert service.get_committed_state_key() == "walking"

    def test_commit_state_writes_through_lock(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")
        service.begin_transition()

        assert service.commit_state("happy") is True
        assert service.get_committed_state_key() == "happy"
        assert service.is_transitioning() is True

    def test_request_missing_state_does_not_queue(
        self, state_service_with_mocks: StateService
    ):
        service = state_service_with_mocks
        service.add_state("idle", "Idle")
        service.set_state("idle")
        service.begin_transition()

        assert service.request_state("nope") is False
        assert service.get_requested_state_key() == "idle"

    def test_lock_expiry_commits_pending_request(
        self, state_service_with_mocks: StateService
    ):
        """is_transitioning() must apply the queue when the lock times out."""
        clock = FakeClock()
        service = state_service_with_mocks
        service._transition_coordinator = TransitionCoordinator(
            transition_repo=None,
            lock_timeout_seconds=1.0,
            clock=clock,
        )
        service.add_state("idle", "Idle")
        service.add_state("happy", "Happy")
        service.set_state("idle")
        service.begin_transition()
        service.request_state("happy")

        clock.advance(1.0)
        assert service.is_transitioning() is False
        assert service.get_committed_state_key() == "happy"
        assert service.get_requested_state_key() == "happy"
