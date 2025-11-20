"""Transition animation player for state changes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtGui

from ...utils.logger import get_logger
from ...utils.paths import ACTION_TRANSITION_DIR

if TYPE_CHECKING:
    from ...window import DoroWindow
    from .service import StateService

logger = get_logger(__name__)


class TransitionPlayer(QtCore.QObject):
    """
    Manages transition animations between states.

    Responsibilities:
    - Find appropriate transition for state changes
    - Load and play transition GIF
    - Lock state changes during playback
    - Load target state GIF after completion
    """

    def __init__(self, window: DoroWindow, state_service: StateService):
        """
        Initialize TransitionPlayer.

        Args:
            window: The main DoroWindow instance
            state_service: StateService for state management
        """
        super().__init__(window)
        self._window = window
        self._state_service = state_service
        self._is_playing = False
        self._target_state_key: Optional[str] = None
        self._transition_movie: Optional[QtGui.QMovie] = None

    def play_transition(self, from_state: str, to_state: str) -> bool:
        """
        Attempt to play transition animation from one state to another.

        If no transition exists or cannot be played, directly loads target state.

        Args:
            from_state: Starting state key
            to_state: Target state key

        Returns:
            True if transition is playing, False if direct switch occurred

        Workflow:
            1. Find transition using priority matching
            2. If found, acquire lock and play transition GIF
            3. When GIF completes, load target state and release lock
            4. If no transition, directly load target state
        """
        # Don't interrupt ongoing transition
        if self._is_playing:
            logger.warning(f"Transition already playing, cannot start {from_state} -> {to_state}")
            return False

        # Find appropriate transition
        transition = self._state_service.find_transition(from_state, to_state)

        # No transition defined - direct switch
        if not transition or not transition.transition_gif_id:
            logger.debug(f"No transition for {from_state} -> {to_state}, switching directly")
            return False

        # Get transition GIF path
        gif_path = self._get_transition_gif_path(transition.transition_gif_id)
        if not gif_path or not gif_path.exists():
            logger.warning(f"Transition GIF not found: {transition.transition_gif_id}, switching directly")
            return False

        # Acquire transition lock
        if not self._state_service.begin_transition():
            logger.warning("Failed to acquire transition lock, switching directly")
            return False

        # Play transition
        logger.info(f"Playing transition: {from_state} -> {to_state} ({transition.transition_gif_id})")
        self._is_playing = True
        self._target_state_key = to_state
        self._load_and_play_transition_gif(gif_path)

        return True

    def _get_transition_gif_path(self, gif_id: str) -> Optional[Path]:
        """
        Get full path to transition GIF.

        Args:
            gif_id: Transition GIF resource ID (filename)

        Returns:
            Full path to GIF file, or None if not found
        """
        # Transition GIFs are stored in res/ACTION/TRANSITION/
        gif_path = ACTION_TRANSITION_DIR / gif_id

        if gif_path.exists():
            return gif_path

        # Try without extension
        if not gif_id.lower().endswith('.gif'):
            gif_path = ACTION_TRANSITION_DIR / f"{gif_id}.gif"
            if gif_path.exists():
                return gif_path

        return None

    def _load_and_play_transition_gif(self, gif_path: Path):
        """
        Load and start playing transition GIF.

        Args:
            gif_path: Path to transition GIF file
        """
        # Clean up previous movie if exists
        if self._transition_movie:
            self._transition_movie.stop()
            self._transition_movie.deleteLater()
            self._transition_movie = None

        # Create QMovie for transition GIF
        self._transition_movie = QtGui.QMovie(str(gif_path))

        # CRITICAL: Set loop count to 1 so transition plays only once
        # Without this, the GIF loops forever and finished signal never fires
        self._transition_movie.setLoopCount(1)

        # Connect completion signal
        self._transition_movie.finished.connect(self._on_transition_complete)

        # Set movie to window's GIF movie (temporarily)
        # This will cause window to render the transition GIF
        old_movie = self._window._gif_movie
        self._window._gif_movie = self._transition_movie

        # Update sprite size from transition GIF
        if self._transition_movie.isValid():
            frame_rect = self._transition_movie.frameRect()
            if frame_rect.width() > 0 and frame_rect.height() > 0:
                self._window._sprite_size = frame_rect.size()
                self._window._apply_window_preferred_size()

        # Start playing
        self._transition_movie.start()
        self._window.update()

        logger.debug(f"Started playing transition GIF: {gif_path.name}")

    def _on_transition_complete(self):
        """
        Called when transition GIF playback completes.

        Loads target state GIF and releases transition lock.
        """
        logger.debug("Transition GIF playback completed")

        # Clean up transition movie
        if self._transition_movie:
            self._transition_movie.stop()
            self._transition_movie.deleteLater()
            self._transition_movie = None

        # Load target state
        if self._target_state_key:
            logger.debug(f"Loading target state: {self._target_state_key}")
            self._load_target_state(self._target_state_key)

        # Release transition lock
        self._state_service.end_transition()

        # Reset state
        self._is_playing = False
        self._target_state_key = None

    def _load_target_state(self, state_key: str):
        """
        Load target state's GIF and apply visual config.

        This is similar to what _on_state_changed() does, but without
        triggering another state change event.

        Args:
            state_key: Target state key to load
        """
        # Get state
        state = self._state_service.get_state(state_key)
        if not state:
            logger.warning(f"Target state not found: {state_key}")
            return

        # Get and load GIF
        gif_resource_id = self._state_service.get_gif_id(state_key)
        if gif_resource_id:
            gif_path = self._state_service.get_gif_path_by_id(gif_resource_id)
            if gif_path:
                self._window._load_gif(str(gif_path))

        # Apply visual config (this will be handled by _on_state_changed already)
        # No need to duplicate here

        logger.info(f"Loaded target state GIF: {state_key}")

    @property
    def is_playing(self) -> bool:
        """Check if a transition is currently playing."""
        return self._is_playing
