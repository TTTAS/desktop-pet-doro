"""State Manager Dialog - manage all states with GIF previews."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import State, StateService
from ...components.gif_player import GifPlayer


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
        self._gif_player = GifPlayer()  # Unified GIF resource management
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
        self._gif_player.clear()  # Clear old GIF players

        visible_keys = sorted(self.service.visible_state_keys())
        for key in visible_keys:
            state = self.service.get_state(key)
            if not state:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # State name with GIF count
            label = state.label or key
            gif_count = self._get_gif_count(state, key)
            gif_info = f" [{gif_count} GIFs]" if gif_count > 1 else ""
            name_item = QtWidgets.QTableWidgetItem(f"{label}\n({key}){gif_info}")
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
                movie = self._gif_player.load(gif_path, size=QtCore.QSize(96, 96))
                if movie:
                    preview_label.setMovie(movie)

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
        Get a GIF path for a state, trying multiple sources.

        Priority:
        1. Multi-GIF subfolder (first file for preview)
        2. state.gif_id (from repository)
        3. Fixed path: res/state/{key}.gif
        """
        # Try multi-GIF subfolder first (use first for preview)
        multi_gifs = self.service.list_gif_paths(key)
        if multi_gifs:
            return multi_gifs[0]

        # Try GIF ID from repository
        if state.gif_id:
            gif_path = self.service.get_gif_path_by_id(state.gif_id)
            if gif_path and gif_path.exists():
                return gif_path

        # Fallback to fixed path: res/state/{key}.gif
        fixed_path = paths.STATE_DIR / f"{key}.gif"
        if fixed_path.exists():
            return fixed_path

        return None

    def _get_gif_count(self, state: State, key: str) -> int:
        """Get the number of GIFs for a state."""
        multi_gifs = self.service.list_gif_paths(key)
        if multi_gifs:
            return len(multi_gifs)
        # Check single file
        if state.gif_id and self.service.get_gif_path_by_id(state.gif_id):
            return 1
        fixed_path = paths.STATE_DIR / f"{key}.gif"
        if fixed_path.exists():
            return 1
        return 0

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
        from .add_dialog import AddStateDialog
        dialog = AddStateDialog(self.service, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_edit_gif(self, state_key: str):
        """Add GIF(s) for a state (supports multiple files)."""
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select GIF file(s)",
            "",
            "GIF Files (*.gif);;All Files (*.*)"
        )

        if not file_paths:
            return

        success_count = 0
        for fp in file_paths:
            if self.service.add_gif(state_key, Path(fp)):
                success_count += 1

        if success_count > 0:
            msg = f"Added {success_count} GIF(s)." if success_count > 1 else "GIF added!"
            QtWidgets.QMessageBox.information(self, "Success", msg)
            self._populate()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to add GIF(s).")

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
        # Edit dialog not yet implemented - see docs/BACKLOG.md
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
        """Clean up GIF resources to prevent memory leaks."""
        self._gif_player.clear()
        super().closeEvent(event)


def show_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show state manager dialog."""
    dialog = StateManagerDialog(service, parent)
    dialog.exec()
