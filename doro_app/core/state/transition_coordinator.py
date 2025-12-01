"""
Transition coordinator for state changes.

Extracted from StateService to improve Single Responsibility Principle.
This coordinator focuses solely on transition animations and locking.
"""

from __future__ import annotations

from typing import Optional

from ...utils.logger import get_logger
from .models import TransitionState, TransitionStateCollection
from .repository import TransitionStateRepository

logger = get_logger(__name__)


class TransitionCoordinator:
    """
    Coordinates state transitions and animations.

    Responsibilities:
    - Find appropriate transition animations
    - Manage transition lock (prevent concurrent state changes)
    - Track transition state
    - Load/store transitions from repository

    Does NOT:
    - Play animations (TransitionPlayer does that)
    - Change states (StateService does that)
    - Know about Qt or UI
    """

    def __init__(self, transition_repo: Optional[TransitionStateRepository]):
        """
        Initialize TransitionCoordinator.

        Args:
            transition_repo: Repository for transition persistence (optional)
        """
        self._transition_repo = transition_repo
        self._transitions = TransitionStateCollection()
        self._is_transitioning = False

    def find(self, from_state: str, to_state: str) -> Optional[TransitionState]:
        """
        Find transition for state change.

        Args:
            from_state: Source state key
            to_state: Target state key

        Returns:
            TransitionState if found, None otherwise
        """
        return self._transitions.find_transition(from_state, to_state)

    def get(self, key: str) -> Optional[TransitionState]:
        """
        Get transition by key.

        Args:
            key: Transition key

        Returns:
            TransitionState if found, None otherwise
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

        Returns:
            True if lock acquired, False if already transitioning

        Usage:
            # Before playing transition GIF
            if coordinator.begin():
                play_transition_gif()
                # ... wait for completion ...
                coordinator.end()
        """
        if self._is_transitioning:
            logger.warning("Transition already in progress, cannot begin new transition")
            return False

        self._is_transitioning = True
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

        self._is_transitioning = False
        logger.debug("Transition lock released")
        return True

    def is_active(self) -> bool:
        """
        Check if transition is in progress.

        Returns:
            True if transition lock is active
        """
        return self._is_transitioning

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

    def add(self, transition: TransitionState) -> None:
        """
        Add a transition to the collection.

        Args:
            transition: TransitionState to add
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
