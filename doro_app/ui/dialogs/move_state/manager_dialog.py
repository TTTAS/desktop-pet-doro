"""Move State Manager Dialog - manage all movement and transition actions."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import State, StateService
from ...components.gif_player import GifPlayer
from ...components.frameless_dialog import FramelessDialog


class MoveStateManagerDialog(FramelessDialog):
    """
    Dialog for managing movement states (actions).

    Allows editing MoveState configurations for transitions and movements.
    """

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("Action Manager", parent)
        self.service = service
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._gif_player = GifPlayer()  # Unified GIF resource management
        self._preview_indices: dict[str, int] = {}
        self._preview_widgets: dict[str, dict] = {}
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = self.content_layout

        # Table - show both movement and transition actions
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Key", "Type", "Action", "Details", "Speed"])

        # Enable grid lines for better visibility
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: rgba(232, 96, 156, 0.20);
            }
            QTableWidget::item {
                border-right: 1px solid rgba(232, 96, 156, 0.15);
            }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        vertical_header = self.table.verticalHeader()
        vertical_header.setStyleSheet("QHeaderView::section { color: #9c6b8a; }")

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_edit)
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
        self._gif_player.clear()
        self._preview_indices.clear()
        self._preview_widgets.clear()

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
            key_item.setForeground(QtGui.QColor("#4a2040"))
            self.table.setItem(row, 0, key_item)

            # Type
            type_item = QtWidgets.QTableWidgetItem("Movement")
            type_item.setForeground(QtGui.QColor("#2e7d32"))  # Green
            self.table.setItem(row, 1, type_item)

            # Action (GIF preview)
            action_label = QtWidgets.QLabel()
            action_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            action_label.setMinimumSize(114, 114)

            state = self.service.get_state(move_state.state_key)
            if state:
                gif_path = self._get_state_gif_path(state, move_state.state_key)
                if gif_path:
                    movie = self._gif_player.load(gif_path, size=QtCore.QSize(96, 96))
                    if movie:
                        action_label.setMovie(movie)

            self.table.setCellWidget(row, 2, action_label)
            self.table.setRowHeight(row, 114)
            # Ensure clicking on GIF preview selects the row
            action_label.mousePressEvent = lambda event, r=row: self.table.selectRow(r)

            # Details (Direction for movement)
            details_item = QtWidgets.QTableWidgetItem(f"Dir: {move_state.direction}")
            details_item.setForeground(QtGui.QColor("#4a2040"))
            self.table.setItem(row, 3, details_item)

            # Speed
            speed_item = QtWidgets.QTableWidgetItem(move_state.default_speed)
            speed_item.setForeground(QtGui.QColor("#4a2040"))
            self.table.setItem(row, 4, speed_item)

        # Add transition actions
        transition_keys = self.service.all_transition_keys()
        for key in sorted(transition_keys):
            transition = self.service.get_transition(key)
            if not transition:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Key (with GIF count)
            gif_paths = self._get_transition_gif_paths(transition.key)
            gif_count = len(gif_paths)
            gif_info = f" [{gif_count} GIFs]" if gif_count > 1 else ""
            key_item = QtWidgets.QTableWidgetItem(f"{transition.key}{gif_info}")
            key_item.setData(QtCore.Qt.ItemDataRole.UserRole, ("transition", transition.key))
            key_item.setForeground(QtGui.QColor("#4a2040"))
            self.table.setItem(row, 0, key_item)

            # Type
            type_item = QtWidgets.QTableWidgetItem("Transition")
            type_item.setForeground(QtGui.QColor("#c0266e"))  # Dark pink
            self.table.setItem(row, 1, type_item)

            # Action (GIF preview with navigation arrows)
            preview_widget = self._create_transition_preview(transition.key, gif_paths)
            self.table.setCellWidget(row, 2, preview_widget)
            self.table.setRowHeight(row, 114)

            # Details (From -> To for transition)
            details_item = QtWidgets.QTableWidgetItem(f"{transition.from_state} → {transition.to_state}")
            details_item.setForeground(QtGui.QColor("#4a2040"))
            self.table.setItem(row, 3, details_item)

            # Speed column: Manage GIFs button
            manage_widget = QtWidgets.QWidget()
            manage_layout = QtWidgets.QVBoxLayout(manage_widget)
            manage_layout.setContentsMargins(5, 5, 5, 5)
            manage_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            manage_btn = QtWidgets.QPushButton("Manage GIFs")
            manage_btn.setMaximumWidth(110)
            manage_btn.clicked.connect(
                lambda checked, r=row, k=transition.key: (
                    self.table.selectRow(r),
                    self._on_manage_transition_gifs(k),
                )
            )
            manage_layout.addWidget(manage_btn)
            self.table.setCellWidget(row, 4, manage_widget)

            # Ensure clicking on cell widgets selects the row
            preview_widget.mousePressEvent = lambda event, r=row: self.table.selectRow(r)
            manage_widget.mousePressEvent = lambda event, r=row: self.table.selectRow(r)

        # Set equal width for all columns
        self._set_equal_column_widths()
        # Force visual refresh
        self.table.viewport().update()

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

        # Fallback: movement state GIF in ACTION/MOVE/
        move_path = paths.STATE_DIR.parent / "ACTION" / "MOVE" / f"{key}.gif"
        if move_path.exists():
            return move_path

        return None

    def _set_equal_column_widths(self):
        """Set all columns to equal width."""
        # Calculate available width (table width minus some padding for scrollbar/borders)
        total_width = self.table.viewport().width()
        column_count = self.table.columnCount()
        column_width = total_width // column_count

        for col in range(column_count):
            self.table.setColumnWidth(col, column_width)

    def _get_transition_gif_paths(self, transition_key: str) -> list[Path]:
        """Get all GIF paths for a transition."""
        gif_paths = self.service.list_transition_gif_paths(transition_key)
        if gif_paths:
            return gif_paths
        # Fallback to single file via transition_gif_id
        transition = self.service.get_transition(transition_key)
        if transition and transition.transition_gif_id:
            gif_path = paths.ACTION_TRANSITION_DIR / transition.transition_gif_id
            if gif_path.exists():
                return [gif_path]
        return []

    def _create_transition_preview(self, key: str, gif_paths: list[Path]) -> QtWidgets.QWidget:
        """Create preview widget with navigation arrows for multi-GIF transitions."""
        count = len(gif_paths)
        self._preview_indices[key] = 0

        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Left arrow
        left_btn = QtWidgets.QPushButton()
        left_btn.setIcon(self._make_arrow_icon("left"))
        left_btn.setIconSize(QtCore.QSize(18, 18))
        left_btn.setFixedSize(30, 30)
        left_btn.setStyleSheet(self._arrow_btn_style())
        left_btn.clicked.connect(lambda checked, k=key: self._navigate_preview(k, -1))
        layout.addWidget(left_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        # Center: preview + counter
        center = QtWidgets.QVBoxLayout()
        center.setSpacing(2)

        preview_label = QtWidgets.QLabel()
        preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        preview_label.setMinimumSize(96, 96)

        if gif_paths:
            movie = self._gif_player.load(gif_paths[0], size=QtCore.QSize(96, 96))
            if movie:
                preview_label.setMovie(movie)

        center.addWidget(preview_label, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        counter_label = QtWidgets.QLabel(f"1/{count}" if count > 0 else "No GIF")
        counter_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        counter_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e8609c;")
        center.addWidget(counter_label, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(center, 1)

        # Right arrow
        right_btn = QtWidgets.QPushButton()
        right_btn.setIcon(self._make_arrow_icon("right"))
        right_btn.setIconSize(QtCore.QSize(18, 18))
        right_btn.setFixedSize(30, 30)
        right_btn.setStyleSheet(self._arrow_btn_style())
        right_btn.clicked.connect(lambda checked, k=key: self._navigate_preview(k, 1))
        layout.addWidget(right_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        if count <= 1:
            left_btn.setVisible(False)
            right_btn.setVisible(False)

        self._preview_widgets[key] = {
            "preview_label": preview_label,
            "counter_label": counter_label,
            "left_btn": left_btn,
            "right_btn": right_btn,
            "gif_paths": gif_paths,
        }

        return container

    @staticmethod
    def _arrow_btn_style() -> str:
        return (
            "QPushButton { background: #fff0f6; border: 1px solid rgba(232,96,156,0.40); "
            "border-radius: 4px; padding: 2px; } "
            "QPushButton:hover { background: #ffe4f0; border-color: #e8609c; }"
        )

    @staticmethod
    def _make_arrow_icon(direction: str) -> QtGui.QIcon:
        px = QtGui.QPixmap(18, 18)
        px.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(px)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#e8609c"))
        if direction == "left":
            points = [QtCore.QPointF(13, 3), QtCore.QPointF(5, 9), QtCore.QPointF(13, 15)]
        else:
            points = [QtCore.QPointF(5, 3), QtCore.QPointF(13, 9), QtCore.QPointF(5, 15)]
        painter.drawPolygon(points)
        painter.end()
        return QtGui.QIcon(px)

    def _navigate_preview(self, key: str, direction: int):
        widgets = self._preview_widgets.get(key)
        if not widgets:
            return
        gif_paths = widgets["gif_paths"]
        if not gif_paths:
            return
        count = len(gif_paths)
        idx = self._preview_indices.get(key, 0)
        idx = (idx + direction) % count
        self._preview_indices[key] = idx

        movie = self._gif_player.load(gif_paths[idx], size=QtCore.QSize(96, 96))
        if movie:
            widgets["preview_label"].setMovie(movie)
        widgets["counter_label"].setText(f"{idx + 1}/{count}")

    def _on_manage_transition_gifs(self, key: str):
        """Open GIF gallery for a transition."""
        from ..state.gif_gallery_dialog import GifGalleryDialog

        gif_paths = self._get_transition_gif_paths(key)
        dialog = GifGalleryDialog(key, key, gif_paths, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            removed = dialog.removed_filenames
            added = dialog.added_paths
            # Release file handles before deleting GIFs (prevents WinError 32)
            dialog._gif_player.clear()
            self._gif_player.clear()
            self._preview_widgets.clear()

            for filename in removed:
                try:
                    self.service.remove_transition_gif(key, filename)
                except Exception:
                    pass  # File locked — will be cleaned up next launch
            for path in added:
                self.service.add_transition_gif(key, path)
            self._populate()

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
            # Release GIF file handles before deletion (prevents WinError 32).
            # GifPlayer.clear() calls setFileName("") on each QMovie to
            # immediately detach the file, so the OS releases the handle.
            self._gif_player.clear()
            self._preview_widgets.clear()

            try:
                if action_type == "movement":
                    success = self.service.remove_move_state(key)
                else:  # transition
                    success = self.service.remove_transition(key)
            except Exception:
                # Data was already removed from the coordinator before GIF
                # cleanup — treat as success so the UI refreshes.
                success = True

            if success:
                self._populate()
            else:
                QtWidgets.QMessageBox.warning(self, "Remove action", f"Failed to remove {action_type_text}.")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up GIF resources to prevent memory leaks."""
        self._gif_player.clear()
        super().closeEvent(event)


def show_move_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent)
    dialog.exec()
