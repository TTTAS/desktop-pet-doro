"""Move State Manager Dialog - manage all movement and transition actions."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import State, StateService


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
        from .edit_dialog import EditMoveStateDialog
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

        from .edit_dialog import EditMoveStateDialog
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


def show_move_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent)
    dialog.exec()
