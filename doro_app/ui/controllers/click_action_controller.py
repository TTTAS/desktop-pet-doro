"""Click action controller - handles click-triggered actions."""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...core.chat.orchestrator import ChatOrchestrator

logger = get_logger(__name__)


class ClickActionController(QtCore.QObject):
    """
    Manages click-triggered actions.

    Responsibilities:
    - Load click actions from file
    - Trigger random actions on click
    - Coordinate with ChatOrchestrator
    """

    # Signals
    action_triggered = QtCore.Signal(str)  # action_message

    def __init__(self, actions_file: Path, chat_orchestrator: ChatOrchestrator):
        """
        Initialize ClickActionController.

        Args:
            actions_file: Path to click actions file
            chat_orchestrator: Chat orchestrator for sending messages
        """
        super().__init__()
        self._actions_file = actions_file
        self._chat_orchestrator = chat_orchestrator
        self._actions: list[str] = []
        self._load_actions()

    def _load_actions(self) -> None:
        """Load actions from file."""
        if not self._actions_file.exists():
            self._actions = []
            return

        try:
            raw = self._actions_file.read_text(encoding="utf-8")
            self._actions = [
                line.strip()
                for line in raw.splitlines()
                if line.strip()
            ]
            logger.debug(f"Loaded {len(self._actions)} click actions")
        except OSError as e:
            logger.warning(f"Failed to load click actions: {e}")
            self._actions = []

    def reload_actions(self) -> None:
        """Reload actions from file."""
        self._load_actions()

    def trigger_random_action(self) -> bool:
        """
        Trigger a random click action.

        Returns:
            True if action was triggered, False if no actions available or chat is busy
        """
        if not self._actions:
            logger.debug("No click actions available")
            return False

        if self._chat_orchestrator.is_inflight:
            logger.debug("Chat is busy, skipping click action")
            return False

        message = random.choice(self._actions).strip()
        if not message:
            return False

        logger.debug(f"Triggering click action: {message}")
        self.action_triggered.emit(message)
        self._chat_orchestrator.send_message(message)
        return True

    @property
    def actions(self) -> list[str]:
        """Get list of loaded actions."""
        return self._actions.copy()

    @property
    def has_actions(self) -> bool:
        """Check if any actions are loaded."""
        return len(self._actions) > 0
