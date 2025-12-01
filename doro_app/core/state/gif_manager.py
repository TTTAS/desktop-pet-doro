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

    def __init__(self, gif_repo: GifRepository):
        """
        Initialize GifManager.

        Args:
            gif_repo: Repository for GIF file operations
        """
        self._gif_repo = gif_repo

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
