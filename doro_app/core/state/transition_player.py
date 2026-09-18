"""Transition animation player for state changes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from ...ui.components.gif_player import GifPlayer
from ...utils.logger import get_logger
from ...utils.paths import ACTION_TRANSITION_DIR  # kept for fallback
from .repository import ANIMATED_EXTENSIONS
from .transition_complete import should_emit_completed_target

if TYPE_CHECKING:
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

    transition_movie_loaded = QtCore.Signal(object, QtCore.QSize)
    transition_completed = QtCore.Signal(str)

    def __init__(self, state_service: StateService):
        """
        Initialize TransitionPlayer.

        Args:
            state_service: StateService for state management
        """
        super().__init__()
        self._state_service = state_service
        self._is_playing = False
        self._target_state_key: str | None = None
        self._gif_player = GifPlayer()
        self._transition_movie: QtGui.QMovie | None = None
        self._last_frame_number = -1
        self._has_played_once = False
        self._quit_hooked = False

        qt_app = QtWidgets.QApplication.instance()
        if qt_app is not None:
            qt_app.aboutToQuit.connect(self.dispose)
            self._quit_hooked = True

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
        if self._is_playing:
            logger.warning(f"Transition already playing, cannot start {from_state} -> {to_state}")
            return False

        transition = self._state_service.find_transition(from_state, to_state)

        if not transition:
            logger.debug(f"No transition for {from_state} -> {to_state}, switching directly")
            return False

        gif_path = self._state_service.get_transition_gif_path(transition.key)

        if (not gif_path or not gif_path.exists()) and transition.transition_gif_id:
            gif_path = self._get_transition_gif_path(transition.transition_gif_id)

        if not gif_path or not gif_path.exists():
            logger.debug(f"No transition GIF for {from_state} -> {to_state}, switching directly")
            return False

        if not self._state_service.begin_transition():
            logger.warning("Failed to acquire transition lock, switching directly")
            return False

        logger.info(
            f"Playing transition: {from_state} -> {to_state} ({transition.transition_gif_id})"
        )
        self._is_playing = True
        self._target_state_key = to_state
        self._last_frame_number = -1
        self._has_played_once = False
        self._load_and_play_transition_gif(gif_path)

        return True

    def dispose(self) -> None:
        """Stop playback and always release the transition lock.

        Call from application teardown so a mid-clip close cannot leave
        ``is_transitioning`` stuck. Safe to call more than once.
        """
        logger.debug("Disposing TransitionPlayer")
        self._gif_player.clear()
        self._transition_movie = None
        self._is_playing = False
        self._target_state_key = None
        # Expire first so a timed-out lock still drains the request queue.
        self._state_service.is_transitioning()
        self._state_service.end_transition()

    def _get_transition_gif_path(self, gif_id: str) -> Path | None:
        """
        Get full path to transition GIF.

        Args:
            gif_id: Transition GIF resource ID (filename)

        Returns:
            Full path to GIF file, or None if not found
        """
        gif_path = ACTION_TRANSITION_DIR / gif_id

        if gif_path.exists():
            return gif_path

        if not any(gif_id.lower().endswith(ext) for ext in ANIMATED_EXTENSIONS):
            for ext in ANIMATED_EXTENSIONS:
                candidate = ACTION_TRANSITION_DIR / f"{gif_id}{ext}"
                if candidate.exists():
                    return candidate

        return None

    def _load_and_play_transition_gif(self, gif_path: Path):
        """
        Load and start playing transition GIF.

        Args:
            gif_path: Path to transition GIF file
        """
        self._gif_player.clear()
        self._transition_movie = None

        self._transition_movie = self._gif_player.load(gif_path)

        if not self._transition_movie:
            logger.error(f"Failed to load transition GIF: {gif_path}")
            self._cleanup_failed_transition()
            return

        self._transition_movie.frameChanged.connect(self._on_transition_frame_changed)

        frame_rect = self._transition_movie.frameRect()
        sprite_size = (
            frame_rect.size()
            if (frame_rect.width() > 0 and frame_rect.height() > 0)
            else QtCore.QSize(200, 200)
        )

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

            if self._last_frame_number > 0 and frame_number <= 0:
                logger.debug(
                    f"Transition loop completed (frame {self._last_frame_number} -> {frame_number})"
                )
                self._has_played_once = True
                self._transition_movie.stop()
                self._on_transition_complete()
            else:
                self._last_frame_number = frame_number
        except (RuntimeError, AttributeError) as e:
            logger.error(f"Error during transition playback: {e}", exc_info=True)
            self._cleanup_failed_transition()

    def _on_transition_complete(self):
        """
        Called when transition GIF playback completes.

        Releases the lock first so a queued request can commit (and may
        start a new transition). Only emit the original target when it is
        still the committed state — otherwise the queued request already
        owns the sprite.
        """
        logger.debug("Transition GIF playback completed")

        target_key = self._target_state_key

        self._gif_player.clear()
        self._transition_movie = None
        self._is_playing = False
        self._target_state_key = None

        self._state_service.end_transition()

        getter = getattr(self._state_service, "get_committed_state_key", None)
        committed = getter() if callable(getter) else self._state_service.get_current_state_key()

        if should_emit_completed_target(target_key, committed):
            logger.debug(f"Emitting transition_completed signal for: {target_key}")
            self.transition_completed.emit(target_key)
        else:
            logger.debug(
                "Skipping stale transition_completed emit "
                f"(target={target_key!r}, committed={committed!r})"
            )

    def _cleanup_failed_transition(self):
        """
        Clean up after a failed transition attempt.

        Releases the transition lock and resets state to prevent deadlock.
        This is called when GIF loading fails or other errors occur.
        """
        logger.warning("Cleaning up failed transition")

        self._gif_player.clear()
        self._transition_movie = None
        self._is_playing = False
        self._target_state_key = None
        self._state_service.end_transition()

    @property
    def is_playing(self) -> bool:
        """Check if a transition is currently playing."""
        return self._is_playing
