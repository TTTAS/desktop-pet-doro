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
            state = self.service.get_state(key)
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
        state = self.service.get_state(state_key)
        if not state or not state.primary_gif_id:
            return

        self.service.gif_repo.delete(state.primary_gif_id)
        self.service.update_state(state_key, primary_gif_id=None)
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
        state = self.service.get_state(self.state_key)
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
        state = self.service.get_state(self.state_key)
        if not state:
            return

        self.service.update_state(self.state_key, primary_gif_id=resource_id)
        self._populate()

    def _on_remove_variant(self):
        """Remove selected variant."""
        item = self.list_widget.currentItem()
        if not item:
            return

        resource_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        state = self.service.get_state(self.state_key)
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

        if self.service.get_state(key):
            QtWidgets.QMessageBox.warning(self, "Add state", "A state with this key already exists.")
            return

        if self.service.is_movement_only_state(key):
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


class MoveStateManagerDialog(QtWidgets.QDialog):
    """
    Dialog for managing movement states (actions).

    Allows editing MoveState configurations for transitions and movements.
    """

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Action Manager - Movement States")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QtWidgets.QLabel("Manage Movement States")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Key", "State", "Direction", "Distance", "Speed"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Buttons
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()

        add_btn = QtWidgets.QPushButton("Add Action")
        add_btn.clicked.connect(self._on_add)
        button_row.addWidget(add_btn)

        edit_btn = QtWidgets.QPushButton("Edit Selected")
        edit_btn.clicked.connect(self._on_edit)
        button_row.addWidget(edit_btn)

        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove)
        button_row.addWidget(remove_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def _populate(self):
        self.table.setRowCount(0)

        move_state_keys = self.service.all_move_state_keys()
        for key in sorted(move_state_keys):
            move_state = self.service.get_move_state(key)
            if not move_state:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Key
            key_item = QtWidgets.QTableWidgetItem(move_state.key)
            key_item.setData(QtCore.Qt.ItemDataRole.UserRole, move_state.key)
            self.table.setItem(row, 0, key_item)

            # State
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(move_state.state_key))

            # Direction
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(move_state.direction))

            # Distance
            distance_text = str(move_state.default_distance) if move_state.default_distance is not None else "-"
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(distance_text))

            # Speed
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(move_state.default_speed))

    def _on_add(self):
        """Add new movement state."""
        dialog = EditMoveStateDialog(self.service, None, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_edit(self):
        """Edit selected movement state."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Edit action", "Please select an action to edit.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        key = key_item.data(QtCore.Qt.ItemDataRole.UserRole)
        dialog = EditMoveStateDialog(self.service, key, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_remove(self):
        """Remove selected movement state."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Remove action", "Please select an action to remove.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        key = key_item.data(QtCore.Qt.ItemDataRole.UserRole)

        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove action",
            f"Remove movement state '{key}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self.service.remove_move_state(key):
                self._populate()
            else:
                QtWidgets.QMessageBox.warning(self, "Remove action", "Failed to remove movement state.")


class EditMoveStateDialog(QtWidgets.QDialog):
    """Dialog for adding or editing a movement state."""

    def __init__(self, service: StateService, move_state_key: Optional[str], parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.move_state_key = move_state_key
        self.is_edit = move_state_key is not None

        title = "Edit Movement State" if self.is_edit else "Add Movement State"
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self._setup_ui()

        if self.is_edit:
            self._load_data()

    def _setup_ui(self):
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Key
        self.key_edit = QtWidgets.QLineEdit()
        if self.is_edit:
            self.key_edit.setEnabled(False)
        layout.addRow("Key (identifier):", self.key_edit)

        # State
        self.state_combo = QtWidgets.QComboBox()
        available_states = self.service.visible_state_keys()
        for state_key in sorted(available_states):
            self.state_combo.addItem(state_key)
        layout.addRow("Associated state:", self.state_combo)

        # Direction
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(["any", "left", "right", "up", "down", "left|right", "up|down"])
        self.direction_combo.setEditable(True)
        layout.addRow("Direction:", self.direction_combo)

        # Distance
        self.distance_edit = QtWidgets.QLineEdit()
        self.distance_edit.setPlaceholderText("Leave empty for default")
        layout.addRow("Default distance (px):", self.distance_edit)

        # Speed
        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(["slow", "med", "fast"])
        layout.addRow("Default speed:", self.speed_combo)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _load_data(self):
        """Load existing move state data."""
        if not self.move_state_key:
            return

        move_state = self.service.get_move_state(self.move_state_key)
        if not move_state:
            return

        self.key_edit.setText(move_state.key)

        # Set state combo
        index = self.state_combo.findText(move_state.state_key)
        if index >= 0:
            self.state_combo.setCurrentIndex(index)

        self.direction_combo.setCurrentText(move_state.direction)

        if move_state.default_distance is not None:
            self.distance_edit.setText(str(move_state.default_distance))

        index = self.speed_combo.findText(move_state.default_speed)
        if index >= 0:
            self.speed_combo.setCurrentIndex(index)

    def _on_accept(self):
        """Validate and save."""
        key = self.key_edit.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Validation", "Key cannot be empty.")
            return

        # Check duplicate key (only for new)
        if not self.is_edit and self.service.get_move_state(key):
            QtWidgets.QMessageBox.warning(self, "Validation", "A movement state with this key already exists.")
            return

        state_key = self.state_combo.currentText()
        if not state_key:
            QtWidgets.QMessageBox.warning(self, "Validation", "Please select an associated state.")
            return

        direction = self.direction_combo.currentText().strip()
        if not direction:
            direction = "any"

        # Parse distance
        distance_text = self.distance_edit.text().strip()
        default_distance = None
        if distance_text:
            try:
                default_distance = float(distance_text)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Validation", "Distance must be a number.")
                return

        default_speed = self.speed_combo.currentText()

        # Create MoveState
        move_state = MoveState(
            key=key,
            state_key=state_key,
            direction=direction,
            default_distance=default_distance,
            default_speed=default_speed,
        )

        # Save
        if self.service.add_move_state(move_state):
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Save", "Failed to save movement state.")


def show_move_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent)
    dialog.exec()
