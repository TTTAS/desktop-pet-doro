"""Dialog manager - manages all application dialogs."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6 import QtWidgets

from ...core.state import StateService
from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...core.action import ActionService

logger = get_logger(__name__)


class DialogManager:
    """
    Manages application dialog windows.

    Responsibilities:
    - Show state management dialogs
    - Show move state management dialogs
    - Show rename dialogs
    - Coordinate dialog lifecycle
    """

    def __init__(
        self,
        parent_window: QtWidgets.QWidget,
        state_service: StateService,
        action_service: Optional["ActionService"] = None,
    ):
        """
        Initialize DialogManager.

        Args:
            parent_window: Parent widget for dialogs
            state_service: State management service
            action_service: Named-action service (Phase 1c). When passed,
                the action manager dialog exposes a Click action card and
                the Edit Action dialog gains the third "Action" option.
        """
        self._parent = parent_window
        self._state_service = state_service
        self._action_service = action_service

    def show_state_manager(self) -> None:
        """Show the state manager dialog."""
        from ..dialogs.state import show_state_manager

        show_state_manager(self._state_service, parent=self._parent)

    def show_move_state_manager(self) -> None:
        """Show the move state manager dialog."""
        from ..dialogs.move_state import show_move_state_manager

        show_move_state_manager(
            self._state_service,
            parent=self._parent,
            action_service=self._action_service,
        )

    def show_add_state_dialog(self) -> str | None:
        """
        Show dialog to add a new state.

        Returns:
            New state key if created, None otherwise
        """
        from ..dialogs.state import show_add_state_dialog

        return show_add_state_dialog(self._state_service, parent=self._parent)

    def show_rename_dialog(self, current_state_key: str) -> bool:
        """
        Show dialog to rename the pet (change name tag).

        Args:
            current_state_key: Current state key

        Returns:
            True if renamed, False if canceled
        """
        if not current_state_key:
            return False

        current_state = self._state_service.get_state(current_state_key)
        if not current_state:
            return False

        text, ok = QtWidgets.QInputDialog.getText(
            self._parent,
            "Rename pet",
            "Name tag:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current_state.name_tag,
        )

        if ok and text.strip():
            self._state_service.update_state(current_state_key, name_tag=text.strip())
            return True

        return False

    def show_remove_state_confirmation(self, state_key: str) -> bool:
        """
        Show confirmation dialog for state removal.

        Args:
            state_key: State key to remove

        Returns:
            True if user confirmed removal
        """
        state = self._state_service.get_state(state_key)
        if not state:
            return False

        reply = QtWidgets.QMessageBox.question(
            self._parent,
            "Remove state",
            f"Remove state '{state.label}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            return self._state_service.remove_state(state_key)

        return False
