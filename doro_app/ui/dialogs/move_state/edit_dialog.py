"""Edit Move State Dialog - add or edit movement and transition actions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import StateService, Transition
from ...components.gif_player import GifPlayer


class EditMoveStateDialog(QtWidgets.QDialog):
    """Dialog for adding or editing a movement state or transition."""

    def __init__(
        self,
        service: StateService,
        move_state_key: Optional[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.service = service
        self.move_state_key = move_state_key
        self.is_edit = move_state_key is not None
        self.action_type = "movement"  # "movement" or "transition"

        title = "Edit Action" if self.is_edit else "Add Action"
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.setMinimumHeight(550)

        # Unified GIF resource management
        self._gif_player = GifPlayer()

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
        self.direction_combo.addItems(
            ["none", "any", "left", "right", "up", "down", "left|right", "up|down"]
        )
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
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _on_action_type_changed(self, action_type_text: str):
        """Handle action type change (Movement/Transition)."""
        is_movement = action_type_text == "Movement"
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
            self, "Select GIF file", "", "GIF Files (*.gif);;All Files (*.*)"
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

        # Clear previous previews
        self._gif_player.clear()
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
        self._gif_player.clear()
        self.preview_label.setMovie(None)

        # Load and display GIF
        movie = self._gif_player.load(gif_path, size=QtCore.QSize(180, 180))
        if not movie:
            self.preview_label.setText("Invalid GIF file")
            return

        self.preview_label.setMovie(movie)

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
            QtWidgets.QMessageBox.warning(
                self, "Validation", "A movement state with this key already exists."
            )
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
                    self, "Warning", "Movement state will be saved, but failed to upload GIF."
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
        key = self.key_edit.text().strip()

        # Check duplicate key (only for new)
        if not self.is_edit and self.service.get_transition(key):
            QtWidgets.QMessageBox.warning(
                self, "Validation", "A transition with this key already exists."
            )
            return

        from_state = self.from_state_combo.currentText()
        to_state = self.to_state_combo.currentText()

        if not from_state or not to_state:
            QtWidgets.QMessageBox.warning(
                self, "Validation", "Please select both from and to states."
            )
            return

        if from_state == to_state:
            QtWidgets.QMessageBox.warning(
                self, "Validation", "From and To states must be different."
            )
            return

        # Upload custom transition GIF if selected
        transition_gif_id = None
        if self.selected_gif_path:
            # Store transition GIF in res/ACTION/TRANSITION/ directory
            try:
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
                    f"Failed to upload GIF: {e}\nTransition will be saved without custom GIF.",
                )

        # Create Transition
        transition = Transition(
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
                QtWidgets.QMessageBox.warning(
                    self, "Save", "Failed to save transition (save_all returned False)."
                )
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Save", f"Failed to save transition: {e}")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up GIF resources to prevent memory leaks."""
        self._gif_player.clear()
        super().closeEvent(event)
