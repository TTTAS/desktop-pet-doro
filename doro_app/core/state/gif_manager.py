"""
GIF resource manager for states.

Extracted from StateService to improve Single Responsibility Principle.
This manager focuses solely on GIF file operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...utils.logger import get_logger
from ..exceptions import GifNotFoundError, GifStorageError
from .repository import GifRepository

logger = get_logger(__name__)


class GifManager:
    """
    Manages GIF resources for states.

    Responsibilities:
    - Store and retrieve GIF files
    - Provide GIF paths by ID or state context
    - Delete GIF resources
    - Delegate actual file I/O to GifRepository

    Does NOT:
    - Know about Qt or UI
    - Manage state lifecycle (StateService does that)
    - Emit events
    - Modify state objects directly
    """

    def __init__(
        self,
        gif_repo: GifRepository,
        transition_gif_repo: Optional[GifRepository] = None,
    ):
        """
        Initialize GifManager.

        Args:
            gif_repo: Repository for state GIF file operations
            transition_gif_repo: Repository for transition GIF file operations
        """
        self._gif_repo = gif_repo
        self._transition_gif_repo = transition_gif_repo

    def get_path_by_id(self, gif_id: str) -> Optional[Path]:
        """
        Get the file path for a GIF resource ID.

        Args:
            gif_id: GIF resource ID

        Returns:
            Absolute path to GIF file or None if not found
        """
        return self._gif_repo.get_path(gif_id)

    def store(self, source_path: Path, context_key: str) -> Optional[str]:
        """
        Store a GIF file.

        Args:
            source_path: Source GIF file path
            context_key: Context identifier (e.g., state key) for organizing storage

        Returns:
            Resource ID or None if failed

        Raises:
            GifNotFoundError: If source file doesn't exist
            GifStorageError: If storage operation fails
        """
        try:
            return self._gif_repo.store_gif(source_path, context_key)
        except (GifNotFoundError, GifStorageError) as e:
            logger.error(f"Failed to store GIF for '{context_key}': {e}")
            return None

    def delete(self, gif_id: str) -> bool:
        """
        Delete a GIF by resource ID.

        Args:
            gif_id: GIF resource ID

        Returns:
            True if deleted, False otherwise
        """
        return self._gif_repo.delete(gif_id)

    # ─────────────────────────────────────────────────────────
    # Multi-GIF Operations
    # ─────────────────────────────────────────────────────────

    def list_gifs(self, state_key: str) -> list[Path]:
        """List all GIF files in a state's subfolder."""
        return self._gif_repo.list_gifs(state_key)

    def pick_random_gif(self, state_key: str) -> Optional[Path]:
        """Pick a random GIF for a state (subfolder first, then single file fallback)."""
        return self._gif_repo.pick_random_gif(state_key)

    def add_gif(self, source_path: Path, state_key: str) -> Optional[str]:
        """Add a GIF to a state's subfolder collection."""
        try:
            return self._gif_repo.add_gif(source_path, state_key)
        except (GifNotFoundError, GifStorageError) as e:
            logger.error(f"Failed to add GIF for '{state_key}': {e}")
            return None

    def remove_gif(self, state_key: str, filename: str) -> bool:
        """Remove a specific GIF from a state's subfolder."""
        return self._gif_repo.remove_gif(state_key, filename)

    def delete_all_gifs(self, state_key: str) -> bool:
        """Delete all GIFs for a state (single file + subfolder)."""
        return self._gif_repo.delete_all_gifs(state_key)

    # ─────────────────────────────────────────────────────────
    # Transition Multi-GIF Operations
    # ─────────────────────────────────────────────────────────

    def list_transition_gifs(self, transition_key: str) -> list[Path]:
        """List all GIF files for a transition."""
        if not self._transition_gif_repo:
            return []
        return self._transition_gif_repo.list_gifs(transition_key)

    def pick_random_transition_gif(self, transition_key: str) -> Optional[Path]:
        """Pick a random GIF for a transition (subfolder first, single file fallback)."""
        if not self._transition_gif_repo:
            return None
        return self._transition_gif_repo.pick_random_gif(transition_key)

    def add_transition_gif(self, source_path: Path, transition_key: str) -> Optional[str]:
        """Add a GIF to a transition's subfolder collection."""
        if not self._transition_gif_repo:
            return None
        try:
            return self._transition_gif_repo.add_gif(source_path, transition_key)
        except (GifNotFoundError, GifStorageError) as e:
            logger.error(f"Failed to add transition GIF for '{transition_key}': {e}")
            return None

    def remove_transition_gif(self, transition_key: str, filename: str) -> bool:
        """Remove a specific GIF from a transition's subfolder."""
        if not self._transition_gif_repo:
            return False
        return self._transition_gif_repo.remove_gif(transition_key, filename)

    def delete_all_transition_gifs(self, transition_key: str) -> bool:
        """Delete all GIFs for a transition (single file + subfolder)."""
        if not self._transition_gif_repo:
            return False
        return self._transition_gif_repo.delete_all_gifs(transition_key)

    # ─────────────────────────────────────────────────────────
    # Path Utilities
    # ─────────────────────────────────────────────────────────

    def get_state_storage_path(self, state_key: str) -> Path:
        """
        Get the expected storage path for a state's GIF.

        Args:
            state_key: State key

        Returns:
            Path where the state's GIF should be stored
        """
        return self._gif_repo.get_state_storage_path(state_key)

    def get_move_storage_path(self, move_key: str) -> Path:
        """
        Get the expected storage path for a movement action's GIF.

        Args:
            move_key: Movement key (e.g., "walking")

        Returns:
            Path where the movement GIF should be stored
        """
        return self._gif_repo.get_move_storage_path(move_key)
