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
        self.setMinimumWidth(700)
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

        # Table (removed Distance column)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Key", "Action", "Direction", "Speed"])

        # Enable grid lines for better visibility
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #333333;
            }
            QTableWidget::item {
                border-right: 1px solid #555555;
            }
        """)

        header = self.table.horizontalHeader()
        # Set all columns to Interactive mode (user can drag to resize)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)

        # Style header: bold and black text
        header.setStyleSheet("QHeaderView::section { font-weight: bold; color: black; }")

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

            # Action (GIF preview)
            action_label = QtWidgets.QLabel()
            action_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            action_label.setMinimumSize(114, 114)

            # Get the state to load its GIF
            state = self.service.get_state(move_state.state_key)
            if state and state.primary_gif_id:
                gif_path = self.service.gif_repo.get_path(state.primary_gif_id)
                if gif_path:
                    movie = QtGui.QMovie(str(gif_path))
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(96, 96))
                        action_label.setMovie(movie)
                        movie.start()

            self.table.setCellWidget(row, 1, action_label)

            # Set row height to match GIF display
            self.table.setRowHeight(row, 114)

            # Direction
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(move_state.direction))

            # Speed (no more Distance column)
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(move_state.default_speed))

        # Set equal width for all columns
        self._set_equal_column_widths()

    def _set_equal_column_widths(self):
        """Set all columns to equal width."""
        # Calculate available width (table width minus some padding for scrollbar/borders)
        total_width = self.table.viewport().width()
        column_count = self.table.columnCount()
        column_width = total_width // column_count

        for col in range(column_count):
            self.table.setColumnWidth(col, column_width)

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
    """Dialog for adding or editing a movement state or transition."""

    def __init__(self, service: StateService, move_state_key: Optional[str], parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.move_state_key = move_state_key
        self.is_edit = move_state_key is not None
        self.action_type = "movement"  # "movement" or "transition"

        title = "Edit Action" if self.is_edit else "Add Action"
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.setMinimumHeight(550)

        # Track preview movie
        self._preview_movie: Optional[QtGui.QMovie] = None

        self._setup_ui()

        if self.is_edit:
            self._load_data()
        else:
            # For new actions, default to movement type
            self._on_action_type_changed("Movement")

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Action Type Selection (only for new actions)
        if not self.is_edit:
            type_layout = QtWidgets.QHBoxLayout()
            type_label = QtWidgets.QLabel("Action Type:")
            type_label.setStyleSheet("color: #ffffff; font-weight: bold;")
            self.type_combo = QtWidgets.QComboBox()
            self.type_combo.addItems(["Movement", "Transition"])
            self.type_combo.currentTextChanged.connect(self._on_action_type_changed)
            type_layout.addWidget(type_label)
            type_layout.addWidget(self.type_combo)
            type_layout.addStretch()
            main_layout.addLayout(type_layout)

        # Form layout
        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setSpacing(12)
        self.form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        # Key (common to both types)
        self.key_edit = QtWidgets.QLineEdit()
        if self.is_edit:
            self.key_edit.setEnabled(False)
        self.key_label = QtWidgets.QLabel("Key (identifier):")
        self.key_label.setStyleSheet("color: #ffffff;")
        self.form_layout.addRow(self.key_label, self.key_edit)

        # Movement-specific fields
        self.state_label = QtWidgets.QLabel("Associated state:")
        self.state_label.setStyleSheet("color: #ffffff;")
        self.state_combo = QtWidgets.QComboBox()
        available_states = self.service.visible_state_keys()
        for state_key in sorted(available_states):
            self.state_combo.addItem(state_key)
        self.state_combo.currentTextChanged.connect(self._on_state_changed)
        self.state_row = self.form_layout.addRow(self.state_label, self.state_combo)

        self.direction_label = QtWidgets.QLabel("Direction:")
        self.direction_label.setStyleSheet("color: #ffffff;")
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(["none", "any", "left", "right", "up", "down", "left|right", "up|down"])
        self.direction_combo.setEditable(True)
        self.direction_row = self.form_layout.addRow(self.direction_label, self.direction_combo)

        self.speed_label = QtWidgets.QLabel("Default speed:")
        self.speed_label.setStyleSheet("color: #ffffff;")
        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(["slow", "med", "fast"])
        self.speed_row = self.form_layout.addRow(self.speed_label, self.speed_combo)

        # Transition-specific fields
        self.from_state_label = QtWidgets.QLabel("From state:")
        self.from_state_label.setStyleSheet("color: #ffffff;")
        self.from_state_combo = QtWidgets.QComboBox()
        for state_key in sorted(available_states):
            self.from_state_combo.addItem(state_key)
        self.from_state_row = self.form_layout.addRow(self.from_state_label, self.from_state_combo)

        self.to_state_label = QtWidgets.QLabel("To state:")
        self.to_state_label.setStyleSheet("color: #ffffff;")
        self.to_state_combo = QtWidgets.QComboBox()
        for state_key in sorted(available_states):
            self.to_state_combo.addItem(state_key)
        self.to_state_row = self.form_layout.addRow(self.to_state_label, self.to_state_combo)

        main_layout.addLayout(self.form_layout)

        # GIF Preview
        preview_group = QtWidgets.QGroupBox("GIF Preview")
        preview_group.setStyleSheet("QGroupBox { color: #ffffff; }")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)

        self.preview_label = QtWidgets.QLabel("Select a state to preview")
        self.preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("background-color: #1a1a1a; color: #888888;")
        preview_layout.addWidget(self.preview_label)

        main_layout.addWidget(preview_group)

        # Info label (dynamic based on action type)
        self.info_label = QtWidgets.QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #a5b4fc; font-size: 11px; padding: 8px;")
        main_layout.addWidget(self.info_label)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _on_action_type_changed(self, action_type_text: str):
        """Handle action type change (Movement/Transition)."""
        is_movement = (action_type_text == "Movement")
        self.action_type = "movement" if is_movement else "transition"

        # Show/hide movement fields
        self.state_label.setVisible(is_movement)
        self.state_combo.setVisible(is_movement)
        self.direction_label.setVisible(is_movement)
        self.direction_combo.setVisible(is_movement)
        self.speed_label.setVisible(is_movement)
        self.speed_combo.setVisible(is_movement)

        # Show/hide transition fields
        self.from_state_label.setVisible(not is_movement)
        self.from_state_combo.setVisible(not is_movement)
        self.to_state_label.setVisible(not is_movement)
        self.to_state_combo.setVisible(not is_movement)

        # Update info label
        if is_movement:
            self.info_label.setText(
                "💡 Movement: LLM determines distance at runtime. Direction can be 'any', 'left', 'right', etc."
            )
        else:
            self.info_label.setText(
                "💡 Transition: Animation plays when changing from one state to another. Default GIF: transition.gif"
            )

    def _on_state_changed(self, state_key: str):
        """Update GIF preview when state selection changes."""
        self._update_preview(state_key)

    def _update_preview(self, state_key: str):
        """Update the GIF preview for the selected state."""
        # Clear previous preview
        if self._preview_movie:
            self._preview_movie.stop()
        self._preview_movie = None
        self.preview_label.setMovie(None)

        if not state_key:
            self.preview_label.setText("No state selected")
            return

        state = self.service.get_state(state_key)
        if not state or not state.primary_gif_id:
            self.preview_label.setText(f"State '{state_key}' has no GIF")
            return

        gif_path = self.service.gif_repo.get_path(state.primary_gif_id)
        if not gif_path:
            self.preview_label.setText("GIF file not found")
            return

        # Load and display GIF
        movie = QtGui.QMovie(str(gif_path))
        if not movie.isValid():
            self.preview_label.setText("Invalid GIF file")
            return

        # Scale to fit preview area
        movie.setScaledSize(QtCore.QSize(180, 180))
        self.preview_label.setMovie(movie)
        self._preview_movie = movie
        movie.start()

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

        index = self.speed_combo.findText(move_state.default_speed)
        if index >= 0:
            self.speed_combo.setCurrentIndex(index)

        # Update preview
        self._update_preview(move_state.state_key)

    def _on_accept(self):
        """Validate and save."""
        key = self.key_edit.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Validation", "Key cannot be empty.")
            return

        if self.action_type == "movement":
            return self._save_movement()
        else:
            return self._save_transition()

    def _save_movement(self):
        """Save movement state."""
        key = self.key_edit.text().strip()

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
            direction = "none"

        default_speed = self.speed_combo.currentText()

        # Create MoveState (no distance field - will be set by LLM)
        move_state = MoveState(
            key=key,
            state_key=state_key,
            direction=direction,
            default_distance=None,
            default_speed=default_speed,
        )

        # Save
        if self.service.add_move_state(move_state):
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Save", "Failed to save movement state.")

    def _save_transition(self):
        """Save transition state."""
        from .state_models import TransitionState

        key = self.key_edit.text().strip()

        # Check duplicate key (only for new)
        if not self.is_edit and self.service.get_transition(key):
            QtWidgets.QMessageBox.warning(self, "Validation", "A transition with this key already exists.")
            return

        from_state = self.from_state_combo.currentText()
        to_state = self.to_state_combo.currentText()

        if not from_state or not to_state:
            QtWidgets.QMessageBox.warning(self, "Validation", "Please select both from and to states.")
            return

        if from_state == to_state:
            QtWidgets.QMessageBox.warning(self, "Validation", "From and To states must be different.")
            return

        # Create TransitionState with default transition.gif
        # TODO: Allow user to upload custom transition GIF
        transition = TransitionState(
            key=key,
            from_state=from_state,
            to_state=to_state,
            transition_gif_id=None,  # Will use default transition.gif
        )

        # Save
        if self.service.add_transition(transition):
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Save", "Failed to save transition.")


def show_move_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent)
    dialog.exec()
