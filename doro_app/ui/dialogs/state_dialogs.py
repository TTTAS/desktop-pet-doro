"""
State management UI dialogs.

These were previously embedded in StateManager (250+ lines of Qt code).
Now they're separate, testable, and reusable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ...utils import paths
from ...core.state import MoveState, State
from ...core.state import GifRepository
from ...core.state import StateService


class StateManagerDialog(QtWidgets.QDialog):
    """
    Dialog for managing states.

    Displays all states with GIF previews and allows editing/removing states.
    """

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("State Manager")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._movies = []  # Keep references to QMovie objects to prevent garbage collection
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QtWidgets.QLabel("Manage States")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["State", "Preview", "Actions"])

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
        # Set all columns to stretch proportionally with window size
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        # Style header: bold and white text
        header.setStyleSheet("QHeaderView::section { font-weight: bold; color: white; }")

        # Style vertical header (row numbers): black text
        vertical_header = self.table.verticalHeader()
        vertical_header.setStyleSheet("QHeaderView::section { color: black; }")

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Buttons
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()

        add_btn = QtWidgets.QPushButton("Add State")
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
        self._movies.clear()  # Clear old movie references

        visible_keys = sorted(self.service.visible_state_keys())
        for key in visible_keys:
            state = self.service.get_state(key)
            if not state:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # State name
            label = state.label or key
            name_item = QtWidgets.QTableWidgetItem(f"{label}\n({key})")
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            name_item.setForeground(QtGui.QColor("#ffffff"))  # White text
            self.table.setItem(row, 0, name_item)

            # Preview (GIF)
            preview_label = QtWidgets.QLabel()
            preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            preview_label.setMinimumSize(114, 114)

            # Try to get GIF path from multiple sources
            gif_path = self._get_state_gif_path(state, key)
            if gif_path:
                movie = QtGui.QMovie(str(gif_path))
                if movie.isValid():
                    movie.setScaledSize(QtCore.QSize(96, 96))
                    preview_label.setMovie(movie)
                    movie.start()
                    self._movies.append(movie)  # Keep reference to prevent garbage collection

            self.table.setCellWidget(row, 1, preview_label)

            # Actions column (Edit GIF button)
            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QVBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 5, 5, 5)
            actions_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            edit_gif_btn = QtWidgets.QPushButton("Edit GIF")
            edit_gif_btn.setMaximumWidth(100)
            edit_gif_btn.clicked.connect(lambda checked, k=key: self._on_edit_gif(k))
            actions_layout.addWidget(edit_gif_btn)

            self.table.setCellWidget(row, 2, actions_widget)

            # Set row height to match GIF display
            self.table.setRowHeight(row, 114)

        # Set equal width for all columns
        self._set_equal_column_widths()

    def _get_state_gif_path(self, state: State, key: str) -> Optional[Path]:
        """
        Get GIF path for a state, trying multiple sources.

        Priority:
        1. state.gif_id (from repository)
        2. Fixed path: res/state/{key}.gif
        """
        # Try GIF ID from repository first
        if state.gif_id:
            gif_path = self.service.get_gif_path_by_id(state.gif_id)
            if gif_path and gif_path.exists():
                return gif_path

        # Fallback to fixed path: res/state/{key}.gif
        fixed_path = paths.STATE_DIR / f"{key}.gif"
        if fixed_path.exists():
            return fixed_path

        return None

    def _set_equal_column_widths(self):
        """Set column widths with appropriate ratios."""
        # Calculate available width (table width minus some padding for scrollbar/borders)
        total_width = self.table.viewport().width()

        # Set proportional widths: State(30%), Preview(50%), Actions(20%)
        self.table.setColumnWidth(0, int(total_width * 0.30))  # State
        self.table.setColumnWidth(1, int(total_width * 0.50))  # Preview
        self.table.setColumnWidth(2, int(total_width * 0.20))  # Actions

    def _on_add(self):
        """Add new state."""
        dialog = AddStateDialog(self.service, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_edit_gif(self, state_key: str):
        """Edit GIF for a state."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select GIF file",
            "",
            "GIF Files (*.gif);;All Files (*.*)"
        )

        if not file_path:
            return

        # Update GIF using service
        if self.service.set_gif(state_key, Path(file_path)):
            QtWidgets.QMessageBox.information(self, "Success", "GIF updated successfully!")
            self._populate()  # Refresh to show new GIF
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to update GIF.")

    def _on_edit(self):
        """Edit selected state."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Edit state", "Please select a state to edit.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        key = key_item.data(QtCore.Qt.ItemDataRole.UserRole)
        # TODO: Implement edit state dialog
        QtWidgets.QMessageBox.information(self, "Edit state", f"Edit functionality for '{key}' will be implemented soon.")

    def _on_remove(self):
        """Remove selected state."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Remove state", "Please select a state to remove.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        key = key_item.data(QtCore.Qt.ItemDataRole.UserRole)

        # Check if state is protected
        if self.service.is_state_protected(key):
            QtWidgets.QMessageBox.warning(
                self,
                "Remove state",
                f"Cannot remove built-in state '{key}'.",
            )
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove state",
            f"Remove state '{key}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self.service.remove_state(key):
                self._populate()
            else:
                QtWidgets.QMessageBox.warning(self, "Remove state", "Failed to remove state.")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up QMovie objects to prevent memory leaks."""
        for movie in self._movies:
            movie.stop()
            movie.deleteLater()
        self._movies.clear()
        super().closeEvent(event)


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


def show_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show state manager dialog."""
    dialog = StateManagerDialog(service, parent)
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
        self.setWindowTitle("Action Manager")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._movies = []  # Keep references to QMovie objects to prevent garbage collection
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QtWidgets.QLabel("Manage Actions")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Table - show both movement and transition actions
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Key", "Type", "Action", "Details", "Speed"])

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
        # Set all columns to stretch proportionally with window size
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        # Style header: bold and white text
        header.setStyleSheet("QHeaderView::section { font-weight: bold; color: white; }")

        # Style vertical header (row numbers): black text
        vertical_header = self.table.verticalHeader()
        vertical_header.setStyleSheet("QHeaderView::section { color: black; }")

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
        self._movies.clear()  # Clear old movie references

        # Add movement actions
        move_state_keys = self.service.all_move_state_keys()
        for key in sorted(move_state_keys):
            move_state = self.service.get_move_state(key)
            if not move_state:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Key
            key_item = QtWidgets.QTableWidgetItem(move_state.key)
            key_item.setData(QtCore.Qt.ItemDataRole.UserRole, ("movement", move_state.key))
            key_item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, 0, key_item)

            # Type
            type_item = QtWidgets.QTableWidgetItem("Movement")
            type_item.setForeground(QtGui.QColor("#4ade80"))  # Green
            self.table.setItem(row, 1, type_item)

            # Action (GIF preview)
            action_label = QtWidgets.QLabel()
            action_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            action_label.setMinimumSize(114, 114)

            state = self.service.get_state(move_state.state_key)
            if state:
                gif_path = self._get_state_gif_path(state, move_state.state_key)
                if gif_path:
                    movie = QtGui.QMovie(str(gif_path))
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(96, 96))
                        action_label.setMovie(movie)
                        movie.start()
                        self._movies.append(movie)

            self.table.setCellWidget(row, 2, action_label)
            self.table.setRowHeight(row, 114)

            # Details (Direction for movement)
            details_item = QtWidgets.QTableWidgetItem(f"Dir: {move_state.direction}")
            details_item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, 3, details_item)

            # Speed
            speed_item = QtWidgets.QTableWidgetItem(move_state.default_speed)
            speed_item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, 4, speed_item)

        # Add transition actions
        transition_keys = self.service.all_transition_keys()
        for key in sorted(transition_keys):
            transition = self.service.get_transition(key)
            if not transition:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Key
            key_item = QtWidgets.QTableWidgetItem(transition.key)
            key_item.setData(QtCore.Qt.ItemDataRole.UserRole, ("transition", transition.key))
            key_item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, 0, key_item)

            # Type
            type_item = QtWidgets.QTableWidgetItem("Transition")
            type_item.setForeground(QtGui.QColor("#fbbf24"))  # Yellow
            self.table.setItem(row, 1, type_item)

            # Action (GIF preview for transition)
            action_label = QtWidgets.QLabel()
            action_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            action_label.setMinimumSize(114, 114)

            if transition.transition_gif_id:
                from ...utils import paths
                gif_path = paths.ACTION_TRANSITION_DIR / transition.transition_gif_id
                if gif_path.exists():
                    movie = QtGui.QMovie(str(gif_path))
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(96, 96))
                        action_label.setMovie(movie)
                        movie.start()
                        self._movies.append(movie)

            self.table.setCellWidget(row, 2, action_label)
            self.table.setRowHeight(row, 114)

            # Details (From -> To for transition)
            details_item = QtWidgets.QTableWidgetItem(f"{transition.from_state} → {transition.to_state}")
            details_item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, 3, details_item)

            # Speed (N/A for transitions)
            speed_item = QtWidgets.QTableWidgetItem("N/A")
            speed_item.setForeground(QtGui.QColor("#888888"))
            self.table.setItem(row, 4, speed_item)

        # Set equal width for all columns
        self._set_equal_column_widths()

    def _get_state_gif_path(self, state: State, key: str) -> Optional[Path]:
        """
        Get GIF path for a state, trying multiple sources.

        Priority:
        1. state.gif_id (from repository)
        2. Fixed path: res/state/{key}.gif
        """
        # Try GIF ID from repository first
        if state.gif_id:
            gif_path = self.service.get_gif_path_by_id(state.gif_id)
            if gif_path and gif_path.exists():
                return gif_path

        # Fallback to fixed path: res/state/{key}.gif
        fixed_path = paths.STATE_DIR / f"{key}.gif"
        if fixed_path.exists():
            return fixed_path

        return None

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
        """Edit selected action (movement or transition)."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Edit action", "Please select an action to edit.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        action_data = key_item.data(QtCore.Qt.ItemDataRole.UserRole)
        action_type, key = action_data

        dialog = EditMoveStateDialog(self.service, key, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_remove(self):
        """Remove selected action (movement or transition)."""
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Remove action", "Please select an action to remove.")
            return

        key_item = self.table.item(row, 0)
        if not key_item:
            return

        action_data = key_item.data(QtCore.Qt.ItemDataRole.UserRole)
        action_type, key = action_data

        action_type_text = "movement" if action_type == "movement" else "transition"
        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove action",
            f"Remove {action_type_text} '{key}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            success = False
            if action_type == "movement":
                success = self.service.remove_move_state(key)
            else:  # transition
                success = self.service.remove_transition(key)

            if success:
                self._populate()
            else:
                QtWidgets.QMessageBox.warning(self, "Remove action", f"Failed to remove {action_type_text}.")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up QMovie objects to prevent memory leaks."""
        for movie in self._movies:
            movie.stop()
            movie.deleteLater()
        self._movies.clear()
        super().closeEvent(event)


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

        # Track selected GIF for upload
        self.selected_gif_path: Optional[Path] = None

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

        # GIF Upload Section
        gif_upload_group = QtWidgets.QGroupBox("GIF File")
        gif_upload_group.setStyleSheet("QGroupBox { color: #ffffff; }")
        gif_upload_layout = QtWidgets.QHBoxLayout(gif_upload_group)

        self.gif_status_label = QtWidgets.QLabel("No GIF selected")
        self.gif_status_label.setStyleSheet("color: #888888;")
        gif_upload_layout.addWidget(self.gif_status_label)

        self.select_gif_btn = QtWidgets.QPushButton("Select GIF")
        self.select_gif_btn.clicked.connect(self._on_select_gif)
        gif_upload_layout.addWidget(self.select_gif_btn)

        main_layout.addWidget(gif_upload_group)

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
            self.gif_status_label.setText(self.selected_gif_path.name)
            self.gif_status_label.setStyleSheet("color: #4ade80;")  # Green color

            # Update preview with the selected GIF
            self._update_preview_from_file(self.selected_gif_path)

    def _update_preview(self, state_key: str):
        """Update the GIF preview for the selected state."""
        # If user has selected a custom GIF, don't override with state GIF
        if self.selected_gif_path:
            return

        # Clear previous preview
        if self._preview_movie:
            self._preview_movie.stop()
        self._preview_movie = None
        self.preview_label.setMovie(None)

        if not state_key:
            self.preview_label.setText("No state selected")
            return

        state = self.service.get_state(state_key)
        if not state or not state.gif_id:
            self.preview_label.setText(f"State '{state_key}' has no GIF")
            return

        gif_path = self.service.get_gif_path_by_id(state.gif_id)
        if not gif_path:
            self.preview_label.setText("GIF file not found")
            return

        # Load and display GIF
        self._load_preview_movie(gif_path)

    def _update_preview_from_file(self, gif_path: Path):
        """Update preview directly from a file path."""
        if not gif_path.exists():
            self.preview_label.setText("File not found")
            return

        self._load_preview_movie(gif_path)

    def _load_preview_movie(self, gif_path: Path):
        """Load and display a GIF in the preview area."""
        # Clear previous preview
        if self._preview_movie:
            self._preview_movie.stop()
        self._preview_movie = None
        self.preview_label.setMovie(None)

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

        # If user selected a GIF, upload it for the associated state
        if self.selected_gif_path:
            if not self.service.set_gif(state_key, self.selected_gif_path):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Movement state will be saved, but failed to upload GIF."
                )

        # Save movement state (service.add_move_state takes individual parameters, not MoveState object)
        try:
            self.service.add_move_state(
                key=key,
                state_key=state_key,
                direction=direction,
                distance=None,
                speed=default_speed,
            )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Save", f"Failed to save movement state: {e}")

    def _save_transition(self):
        """Save transition state."""
        from ...core.state import TransitionState

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

        # Upload custom transition GIF if selected
        transition_gif_id = None
        if self.selected_gif_path:
            # Store transition GIF in res/ACTION/TRANSITION/ directory
            try:
                from ...utils import paths
                import shutil

                # Ensure transition directory exists
                paths.ACTION_TRANSITION_DIR.mkdir(parents=True, exist_ok=True)

                # Sanitize key for filename
                safe_key = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
                dest_filename = f"{safe_key}.gif"
                dest_path = paths.ACTION_TRANSITION_DIR / dest_filename

                # Copy the GIF file
                shutil.copy2(self.selected_gif_path, dest_path)

                # Use relative path as resource ID: "../../ACTION/TRANSITION/filename.gif"
                # or just "filename.gif" if we store it relative to ACTION/TRANSITION
                transition_gif_id = dest_filename

            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    f"Failed to upload GIF: {e}\nTransition will be saved without custom GIF."
                )

        # Create TransitionState
        transition = TransitionState(
            key=key,
            from_state=from_state,
            to_state=to_state,
            transition_gif_id=transition_gif_id,  # None = use default transition.gif
        )

        # Save
        try:
            result = self.service.add_transition(transition)
            if result:
                self.accept()
            else:
                QtWidgets.QMessageBox.warning(self, "Save", "Failed to save transition (save_all returned False).")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Save", f"Failed to save transition: {e}")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up QMovie object to prevent memory leaks."""
        if self._preview_movie:
            self._preview_movie.stop()
            self._preview_movie.deleteLater()
            self._preview_movie = None
        super().closeEvent(event)


def show_move_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent)
    dialog.exec()
