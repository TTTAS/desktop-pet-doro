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
        self.selected_gif_paths: list[Path] = []
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
        self.gif_label.setStyleSheet("color: #9c6b8a;")
        gif_layout.addWidget(self.gif_label)

        select_gif_btn = QtWidgets.QPushButton("Select GIF(s)")
        select_gif_btn.clicked.connect(self._on_select_gif)
        gif_layout.addWidget(select_gif_btn)

        layout.addRow("GIF file(s):", gif_layout)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_select_gif(self):
        """Handle GIF file selection (supports multiple files)."""
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select GIF file(s)",
            "",
            "GIF Files (*.gif);;All Files (*.*)"
        )

        if file_paths:
            self.selected_gif_paths = [Path(p) for p in file_paths]
            count = len(self.selected_gif_paths)
            if count == 1:
                self.gif_label.setText(self.selected_gif_paths[0].name)
            else:
                self.gif_label.setText(f"{count} GIFs selected")
            self.gif_label.setStyleSheet("color: #4a2040;")

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

        # Set GIF(s) if selected
        if self.selected_gif_paths:
            if len(self.selected_gif_paths) == 1:
                if not self.service.set_gif(key, self.selected_gif_paths[0]):
                    QtWidgets.QMessageBox.warning(self, "Add state", "State created but failed to set GIF.")
                    self.accept()
                    return
            else:
                for gif_path in self.selected_gif_paths:
                    self.service.add_gif(key, gif_path)

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
