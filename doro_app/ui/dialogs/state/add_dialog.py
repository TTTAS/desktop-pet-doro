"""Add State Dialog - create new states."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from ....core.state import StateService


class AddStateDialog(QtWidgets.QDialog):
    """Dialog for creating a new state."""

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Add new state")
        self.selected_gif_path: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QFormLayout(self)

        self.key_edit = QtWidgets.QLineEdit()
        layout.addRow("Unique state key:", self.key_edit)

        self.label_edit = QtWidgets.QLineEdit()
        layout.addRow("Display name:", self.label_edit)

        # GIF selection
        gif_layout = QtWidgets.QHBoxLayout()
        self.gif_label = QtWidgets.QLabel("No GIF selected")
        self.gif_label.setStyleSheet("color: #888888;")
        gif_layout.addWidget(self.gif_label)

        select_gif_btn = QtWidgets.QPushButton("Select GIF")
        select_gif_btn.clicked.connect(self._on_select_gif)
        gif_layout.addWidget(select_gif_btn)

        layout.addRow("GIF file:", gif_layout)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_select_gif(self):
        """Handle GIF file selection."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select GIF file",
            "",
            "GIF Files (*.gif);;All Files (*.*)"
        )

        if file_path:
            self.selected_gif_path = Path(file_path)
            self.gif_label.setText(self.selected_gif_path.name)
            self.gif_label.setStyleSheet("color: #ffffff;")

    def _on_accept(self):
        key = self.key_edit.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Add state", "Key cannot be empty.")
            return

        if self.service.get_state(key):
            QtWidgets.QMessageBox.warning(self, "Add state", "A state with this key already exists.")
            return

        if self.service.is_movement_only_state(key):
            QtWidgets.QMessageBox.warning(self, "Add state", "This key is reserved for movement animations.")
            return

        label = self.label_edit.text().strip() or key.capitalize()

        # Create state
        state = self.service.add_state(key, label)
        if not state:
            QtWidgets.QMessageBox.warning(self, "Add state", "Failed to create state.")
            return

        # Set GIF if selected
        if self.selected_gif_path:
            if not self.service.set_gif(key, self.selected_gif_path):
                QtWidgets.QMessageBox.warning(self, "Add state", "State created but failed to set GIF.")
                self.accept()
                return

        self.accept()


def show_add_state_dialog(service: StateService, parent: Optional[QtWidgets.QWidget] = None) -> Optional[str]:
    """
    Show add state dialog.

    Returns:
        Created state key or None if cancelled
    """
    dialog = AddStateDialog(service, parent)
    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        return dialog.key_edit.text().strip()
    return None
