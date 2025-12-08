"""Transition animation player for state changes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtGui

from ...ui.components.gif_player import GifPlayer
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

    Signals:
    - transition_movie_loaded: Emitted when transition GIF is loaded (QMovie, QSize)
    - transition_completed: Emitted when transition animation completes (str: target_state_key)
    """

    # Signals to decouple from Window
    transition_movie_loaded = QtCore.Signal(object, QtCore.QSize)  # QMovie, sprite_size
    transition_completed = QtCore.Signal(str)  # target_state_key

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
        self._gif_player = GifPlayer()
        self._transition_movie: Optional[QtGui.QMovie] = None
        self._last_frame_number = -1
        self._has_played_once = False

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
            logger.warning(
                f"Transition GIF not found: {transition.transition_gif_id}, switching directly"
            )
            return False

        # Acquire transition lock
        if not self._state_service.begin_transition():
            logger.warning("Failed to acquire transition lock, switching directly")
            return False

        # Play transition
        logger.info(
            f"Playing transition: {from_state} -> {to_state} ({transition.transition_gif_id})"
        )
        self._is_playing = True
        self._target_state_key = to_state
        self._last_frame_number = -1
        self._has_played_once = False
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
        if not gif_id.lower().endswith(".gif"):
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
        # Clear all previous movies using GifPlayer
        self._gif_player.clear()
        self._transition_movie = None

        # Load transition GIF using GifPlayer
        self._transition_movie = self._gif_player.load(gif_path)

        if not self._transition_movie:
            logger.error(f"Failed to load transition GIF: {gif_path}")
            # CRITICAL: Release lock if loading failed
            self._cleanup_failed_transition()
            return

        # CRITICAL: Monitor frame changes to detect when one loop completes
        # QMovie doesn't have setLoopCount in PySide6, so we detect loop completion manually
        # When frameNumber wraps back to 0, we know the loop completed
        self._transition_movie.frameChanged.connect(self._on_transition_frame_changed)

        # Update sprite size from transition GIF
        frame_rect = self._transition_movie.frameRect()
        sprite_size = (
            frame_rect.size()
            if (frame_rect.width() > 0 and frame_rect.height() > 0)
            else QtCore.QSize(200, 200)
        )

        # Emit signal to notify Window (decouples TransitionPlayer from Window internals)
        self.transition_movie_loaded.emit(self._transition_movie, sprite_size)

        logger.debug(f"Started playing transition GIF: {gif_path.name}")

    def _on_transition_frame_changed(self, frame_number: int):
        """
        Monitor frame changes to detect when transition GIF completes one loop.

        Args:
            frame_number: Current frame number from QMovie
        """
        try:
            if not self._is_playing or not self._transition_movie:
                return

            # Detect loop completion: frame number wraps back to 0 or -1 after we've played
            if self._last_frame_number > 0 and frame_number <= 0:
                # One complete loop detected
                logger.debug(
                    f"Transition loop completed (frame {self._last_frame_number} -> {frame_number})"
                )
                self._has_played_once = True
                # Stop the movie and trigger completion
                self._transition_movie.stop()
                self._on_transition_complete()
            else:
                self._last_frame_number = frame_number
        except (RuntimeError, AttributeError) as e:
            # RuntimeError: Qt object deleted during playback
            # AttributeError: Object state inconsistent (e.g., _transition_movie cleared)
            # Critical: Must clean up to prevent transition lock leak
            logger.error(f"Error during transition playback: {e}", exc_info=True)
            self._cleanup_failed_transition()

    def _on_transition_complete(self):
        """
        Called when transition GIF playback completes.

        Emits signal to notify Window to load target state, then releases transition lock.
        """
        logger.debug("Transition GIF playback completed")

        # Clear all transition movies using GifPlayer
        self._gif_player.clear()
        self._transition_movie = None

        # Store target for signal emission
        target_key = self._target_state_key

        # Release transition lock BEFORE emitting signal
        self._state_service.end_transition()

        # Reset state
        self._is_playing = False
        self._target_state_key = None

        # Emit signal to notify Window to load target state
        if target_key:
            logger.debug(f"Emitting transition_completed signal for: {target_key}")
            self.transition_completed.emit(target_key)

    def _cleanup_failed_transition(self):
        """
        Clean up after a failed transition attempt.

        Releases the transition lock and resets state to prevent deadlock.
        This is called when GIF loading fails or other errors occur.
        """
        logger.warning("Cleaning up failed transition")

        # Clear resources
        self._gif_player.clear()
        self._transition_movie = None

        # Release transition lock
        self._state_service.end_transition()

        # Reset state
        self._is_playing = False
        self._target_state_key = None

    @property
    def is_playing(self) -> bool:
        """Check if a transition is currently playing."""
        return self._is_playing
