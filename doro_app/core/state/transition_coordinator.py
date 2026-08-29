"""
Transition coordinator for state changes.

Extracted from StateService to improve Single Responsibility Principle.
This coordinator focuses solely on transition animations and locking.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from ...utils.logger import get_logger
from .models import Transition, TransitionCollection
from .repository import TransitionRepository

logger = get_logger(__name__)

# Fallback so a missed end() cannot pin is_transitioning forever.
# Transition GIFs in this project are short; 5s is longer than one loop
# plus a generous buffer. Callers may pass a tighter value.
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


class TransitionCoordinator:
    """
    Coordinates state transitions and animations.

    Responsibilities:
    - Find appropriate transition animations
    - Manage transition lock (prevent concurrent state changes)
    - Expire the lock if end() is never called
    - Track transition state
    - Load/store transitions from repository

    Does NOT:
    - Play animations (TransitionPlayer does that)
    - Change states (StateService does that)
    - Know about Qt or UI
    """

    def __init__(
        self,
        transition_repo: Optional[TransitionRepository],
        *,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        """
        Initialize TransitionCoordinator.

        Args:
            transition_repo: Repository for transition persistence (optional)
            lock_timeout_seconds: Seconds after begin() before the lock
                auto-releases. Prevents a missed end() from freezing the pet.
            clock: Monotonic clock used for the timeout (injectable in tests)
        """
        self._transition_repo = transition_repo
        self._transitions = TransitionCollection()
        self._is_transitioning = False
        self._lock_timeout_seconds = lock_timeout_seconds
        self._clock = clock
        self._lock_acquired_at: Optional[float] = None

    def find(self, from_state: str, to_state: str) -> Optional[Transition]:
        """
        Find transition for state change.

        Args:
            from_state: Source state key
            to_state: Target state key

        Returns:
            Transition if found, None otherwise
        """
        return self._transitions.find_transition(from_state, to_state)

    def get(self, key: str) -> Optional[Transition]:
        """
        Get transition by key.

        Args:
            key: Transition key

        Returns:
            Transition if found, None otherwise
        """
        return self._transitions.get(key)

    def all_keys(self) -> list[str]:
        """
        List all transition keys.

        Returns:
            List of transition keys
        """
        return self._transitions.all_keys()

    def begin(self) -> bool:
        """
        Begin transition, lock state changes.

        Prevents non-forced state changes during transition playback.
        Only forced state changes (force=True) can bypass this lock.
        An expired lock is released first so a missed end() cannot block
        the next transition forever.

        Returns:
            True if lock acquired, False if already transitioning

        Usage:
            # Before playing transition GIF
            if coordinator.begin():
                play_transition_gif()
                # ... wait for completion ...
                coordinator.end()
        """
        self.expire_if_needed()
        if self._is_transitioning:
            logger.warning("Transition already in progress, cannot begin new transition")
            return False

        self._is_transitioning = True
        self._lock_acquired_at = self._clock()
        logger.debug("Transition lock acquired")
        return True

    def end(self) -> bool:
        """
        End transition, unlock state changes.

        Allows normal state changes to proceed after transition playback.

        Returns:
            True if lock released, False if no transition was in progress

        Usage:
            # After transition GIF completes
            coordinator.end()
        """
        if not self._is_transitioning:
            logger.warning("No transition in progress, cannot end")
            return False

        self._release_lock()
        logger.debug("Transition lock released")
        return True

    def expire_if_needed(self) -> bool:
        """
        Release the lock if it has been held longer than the timeout.

        Returns:
            True if the lock was expired and released, False otherwise
        """
        if not self._is_transitioning:
            return False
        if self._lock_acquired_at is None:
            return False
        elapsed = self._clock() - self._lock_acquired_at
        if elapsed < self._lock_timeout_seconds:
            return False

        logger.warning(
            "Transition lock expired after %.2fs (timeout=%.2fs)",
            elapsed,
            self._lock_timeout_seconds,
        )
        self._release_lock()
        return True

    def is_active(self) -> bool:
        """
        Check if transition is in progress.

        Expired locks are treated as inactive.

        Returns:
            True if transition lock is active
        """
        self.expire_if_needed()
        return self._is_transitioning

    def _release_lock(self) -> None:
        self._is_transitioning = False
        self._lock_acquired_at = None

    def load_from_repo(self) -> None:
        """
        Load transitions from repository.

        This should be called during initialization to populate
        the transitions collection from persistent storage.
        """
        if not self._transition_repo:
            logger.debug("No transition repository, skipping load")
            return

        transitions = self._transition_repo.load_all()
        for transition in transitions.values():
            self._transitions.add(transition)

        logger.debug(f"Loaded {len(transitions)} transitions from repository")

    def add(self, transition: Transition) -> None:
        """
        Add a transition to the collection.

        Args:
            transition: Transition to add
        """
        self._transitions.add(transition)

    def remove(self, key: str) -> bool:
        """
        Remove a transition from the collection.

        Args:
            key: Transition key to remove

        Returns:
            True if removed, False if not found
        """
        return self._transitions.remove(key)

    def get_all_items(self) -> dict[str, Transition]:
        """
        Get all transitions as a dictionary (for persistence).

        Returns:
            Dictionary mapping transition keys to Transition objects
        """
        return self._transitions.all_items()
