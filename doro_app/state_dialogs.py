"""
State management UI dialogs.

These were previously embedded in StateManager (250+ lines of Qt code).
Now they're separate, testable, and reusable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .state_models import MoveState, State
from .state_repository import GifRepository
from .state_service import StateService


class StateGifManagerDialog(QtWidgets.QDialog):
    """
    Dialog for managing GIFs for all states.

    Old location: StateManager.show_state_gif_manager()
    """

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("State GIFs")
        self.setMinimumWidth(680)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["State", "Preview", "GIF Path", "Actions"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def _populate(self):
        self.table.setRowCount(0)
        visible_keys = sorted(self.service.visible_state_keys())

        for row, key in enumerate(visible_keys):
            state = self.service.states.get(key)
            if not state:
                continue

            self.table.insertRow(row)

            # State name
            label = state.label or key
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"{label}\n({key})"))

            # Preview
            preview_label = QtWidgets.QLabel()
            preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            preview_label.setMinimumSize(114, 114)

            if state.primary_gif_id:
                gif_path = self.service.gif_repo.get_path(state.primary_gif_id)
                if gif_path:
                    movie = QtGui.QMovie(str(gif_path))
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(96, 96))
                        preview_label.setMovie(movie)
                        movie.start()

            self.table.setCellWidget(row, 1, preview_label)

            # GIF path
            gif_info = self._gif_display_text(state)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(gif_info))

            # Actions
            btn_container = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(0, 0, 0, 0)

            set_btn = QtWidgets.QPushButton("Set GIF")
            set_btn.clicked.connect(lambda checked=False, k=key: self._on_set_gif(k))
            btn_layout.addWidget(set_btn)

            clear_btn = QtWidgets.QPushButton("Clear")
            clear_btn.clicked.connect(lambda checked=False, k=key: self._on_clear_gif(k))
            btn_layout.addWidget(clear_btn)

            self.table.setCellWidget(row, 3, btn_container)

    def _gif_display_text(self, state: State) -> str:
        """Generate display text for GIF info."""
        if not state.primary_gif_id:
            return "(no GIF)"

        gif_path = self.service.gif_repo.get_path(state.primary_gif_id)
        text = str(gif_path) if gif_path else "(no GIF)"

        variant_count = len(state.variant_gif_ids)
        if variant_count > 1:  # Subtract primary
            text += f" (+{variant_count - 1} variants)"

        return text

    def _on_set_gif(self, state_key: str):
        """Handle Set GIF button click."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Select GIF for '{state_key}'",
            str(self.service.gif_repo.storage_dir),
            "GIF files (*.gif)",
        )
        if not file_path:
            return

        if self.service.set_primary_gif(state_key, Path(file_path)):
            self._populate()
        else:
            QtWidgets.QMessageBox.warning(self, "Set GIF", "Failed to load the selected GIF.")

    def _on_clear_gif(self, state_key: str):
        """Handle Clear GIF button click."""
        state = self.service.states.get(state_key)
        if not state or not state.primary_gif_id:
            return

        self.service.gif_repo.delete(state.primary_gif_id)
        updated = state.with_changes(primary_gif_id=None)
        self.service.states.add(updated)
        self._populate()


class GifVariantDialog(QtWidgets.QDialog):
    """
    Dialog for managing GIF variants for a single state.

    Old location: StateManager.show_state_gif_collection()
    """

    def __init__(
        self,
        service: StateService,
        state_key: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.service = service
        self.state_key = state_key
        self.setWindowTitle(f"GIF variants · {state_key}")
        self.setMinimumWidth(520)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        # Info label
        info_label = QtWidgets.QLabel(
            "Manage the primary animation and additional variants. "
            "Doro will randomly pick one when this state is active."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #a5b4fc; font-size: 11px;")
        layout.addWidget(info_label)

        # List widget
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget, stretch=1)

        # Preview
        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setFixedHeight(180)
        self.preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_label)

        # Buttons
        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(12)

        add_btn = QtWidgets.QPushButton("Add variant")
        add_btn.clicked.connect(self._on_add_variant)
        button_row.addWidget(add_btn)

        set_main_btn = QtWidgets.QPushButton("Set as main")
        set_main_btn.clicked.connect(self._on_set_main)
        button_row.addWidget(set_main_btn)

        remove_btn = QtWidgets.QPushButton("Remove variant")
        remove_btn.clicked.connect(self._on_remove_variant)
        button_row.addWidget(remove_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

        # Connect selection change to preview
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

        # Track current preview movie
        self._preview_movie: Optional[QtGui.QMovie] = None

    def _populate(self):
        self.list_widget.clear()
        state = self.service.states.get(self.state_key)
        if not state:
            return

        # Add primary
        if state.primary_gif_id:
            item = QtWidgets.QListWidgetItem("Primary GIF")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, state.primary_gif_id)
            self.list_widget.addItem(item)

        # Add variants
        for idx, variant_id in enumerate(state.variant_gif_ids, start=1):
            if variant_id == state.primary_gif_id:
                continue
            item = QtWidgets.QListWidgetItem(f"Variant {idx}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, variant_id)
            self.list_widget.addItem(item)

        # Select first
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_selection_changed(self):
        """Update preview when selection changes."""
        item = self.list_widget.currentItem()
        if not item:
            self._clear_preview()
            return

        resource_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not resource_id:
            self._clear_preview()
            return

        gif_path = self.service.gif_repo.get_path(resource_id)
        if not gif_path:
            self._clear_preview()
            return

        self._show_preview(gif_path)

    def _show_preview(self, path: Path):
        """Show GIF preview."""
        self._clear_preview()

        movie = QtGui.QMovie(str(path))
        if not movie.isValid():
            self.preview_label.setText("Invalid GIF")
            return

        self.preview_label.setMovie(movie)
        self._preview_movie = movie
        movie.start()

    def _clear_preview(self):
        """Clear preview."""
        if self._preview_movie:
            self._preview_movie.stop()
        self._preview_movie = None
        self.preview_label.setMovie(None)
        self.preview_label.setText("No GIF selected")

    def _on_add_variant(self):
        """Add a new variant."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Add GIF variant for '{self.state_key}'",
            str(self.service.gif_repo.storage_dir),
            "GIF files (*.gif)",
        )
        if not file_path:
            return

        if self.service.add_gif_variant(self.state_key, Path(file_path)):
            self._populate()
        else:
            QtWidgets.QMessageBox.warning(self, "Add variant", "Failed to add GIF variant.")

    def _on_set_main(self):
        """Set selected variant as primary."""
        item = self.list_widget.currentItem()
        if not item:
            return

        resource_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        state = self.service.states.get(self.state_key)
        if not state:
            return

        updated = state.with_changes(primary_gif_id=resource_id)
        self.service.states.add(updated)
        self._populate()

    def _on_remove_variant(self):
        """Remove selected variant."""
        item = self.list_widget.currentItem()
        if not item:
            return

        resource_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        state = self.service.states.get(self.state_key)
        if not state or resource_id == state.primary_gif_id:
            QtWidgets.QMessageBox.information(
                self,
                "Remove variant",
                "Select a variant entry to remove (not primary).",
            )
            return

        if self.service.remove_gif_variant(self.state_key, resource_id):
            self._populate()


class AddStateDialog(QtWidgets.QDialog):
    """Dialog for creating a new state."""

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Add new state")
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QFormLayout(self)

        self.key_edit = QtWidgets.QLineEdit()
        layout.addRow("Unique state key:", self.key_edit)

        self.label_edit = QtWidgets.QLineEdit()
        layout.addRow("Display name:", self.label_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self):
        key = self.key_edit.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Add state", "Key cannot be empty.")
            return

        if self.service.states.get(key):
            QtWidgets.QMessageBox.warning(self, "Add state", "A state with this key already exists.")
            return

        if self.service.move_states.is_movement_only(key):
            QtWidgets.QMessageBox.warning(self, "Add state", "This key is reserved for movement animations.")
            return

        label = self.label_edit.text().strip() or key.capitalize()

        # Create state
        if self.service.add_state(key, label):
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Add state", "Failed to create state.")


def show_state_gif_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show state GIF manager dialog."""
    dialog = StateGifManagerDialog(service, parent)
    dialog.exec()


def show_gif_variant_dialog(service: StateService, state_key: str, parent: Optional[QtWidgets.QWidget] = None):
    """Show GIF variant manager for a state."""
    dialog = GifVariantDialog(service, state_key, parent)
    dialog.exec()


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
