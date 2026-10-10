"""Edit Move State Dialog - add or edit movement and transition actions."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ....core.action import ActionService
from ....core.action.repository import (
    CLICK_ACTION_KEY,
    PET_CLICK_ACTION_KEY,
    PET_DRAG_ACTION_KEY,
)
from ....core.state import StateService, Transition
from ...components.frameless_dialog import FramelessDialog
from ...components.gif_player import GifPlayer


class EditMoveStateDialog(FramelessDialog):
    """Dialog for adding or editing a movement state, transition, or named action."""

    def __init__(
        self,
        service: StateService,
        move_state_key: str | None,
        parent: QtWidgets.QWidget | None = None,
        *,
        action_service: ActionService | None = None,
        edit_action_key: str | None = None,
    ):
        # action edit mode wins over move_state edit semantics.
        self._edit_action_key = edit_action_key
        is_action_edit = edit_action_key is not None
        title = "Edit Action" if (move_state_key is not None or is_action_edit) else "Add Action"
        super().__init__(title, parent)
        self.service = service
        self._action_service = action_service
        self.move_state_key = move_state_key
        self.is_edit = move_state_key is not None or is_action_edit
        self.action_type = "action" if is_action_edit else "movement"

        self.setMinimumWidth(600)
        self.setMinimumHeight(550)

        # Unified GIF resource management
        self._gif_player = GifPlayer()

        # Track selected GIF for upload
        self.selected_gif_path: Path | None = None
        self._clear_pet_click_gif = False

        self._setup_ui()

        if is_action_edit:
            self._on_action_type_changed("Action")
            self._load_action_data()
        elif self.is_edit:
            self._load_data()
        else:
            # For new actions, default to movement type
            self._on_action_type_changed("Movement")

    def _setup_ui(self):
        main_layout = self.content_layout

        # Action Type Selection (only for new actions)
        if not self.is_edit:
            type_layout = QtWidgets.QHBoxLayout()
            type_label = QtWidgets.QLabel("Action Type:")
            type_label.setStyleSheet("color: #e8609c; font-weight: bold;")
            self.type_combo = QtWidgets.QComboBox()
            self.type_combo.addItems(["Movement", "Transition"])
            # The "Action" option is gated on an injected ActionService so
            # legacy callers that don't know about named actions keep their
            # existing two-option menu.
            if self._action_service is not None:
                self.type_combo.addItem("Action")
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
        self.key_label.setStyleSheet("color: #4a2040;")
        self.form_layout.addRow(self.key_label, self.key_edit)

        self.named_action_label = QtWidgets.QLabel("觸發方式：")
        self.named_action_combo = QtWidgets.QComboBox()
        self.named_action_combo.addItem("Doro 幫你點畫面", CLICK_ACTION_KEY)
        self.named_action_combo.addItem("Doro 被點擊", PET_CLICK_ACTION_KEY)
        self.named_action_combo.addItem("Doro 被拖曳", PET_DRAG_ACTION_KEY)
        self.named_action_combo.setEnabled(not self.is_edit)
        if self._edit_action_key:
            self.named_action_combo.setCurrentIndex(
                self.named_action_combo.findData(self._edit_action_key)
            )
        self.named_action_combo.currentIndexChanged.connect(self._on_named_action_changed)
        self.form_layout.addRow(self.named_action_label, self.named_action_combo)

        # Movement-specific fields
        self.state_label = QtWidgets.QLabel("Associated state:")
        self.state_label.setStyleSheet("color: #4a2040;")
        self.state_combo = QtWidgets.QComboBox()
        available_states = self.service.visible_state_keys()
        for state_key in sorted(available_states):
            self.state_combo.addItem(state_key)
        self.state_combo.currentTextChanged.connect(self._on_state_changed)
        self.state_row = self.form_layout.addRow(self.state_label, self.state_combo)

        self.direction_label = QtWidgets.QLabel("Direction:")
        self.direction_label.setStyleSheet("color: #4a2040;")
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(
            ["none", "any", "left", "right", "up", "down", "left|right", "up|down"]
        )
        self.direction_combo.setEditable(True)
        self.direction_row = self.form_layout.addRow(self.direction_label, self.direction_combo)

        self.speed_label = QtWidgets.QLabel("Default speed:")
        self.speed_label.setStyleSheet("color: #4a2040;")
        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(["slow", "med", "fast"])
        self.speed_row = self.form_layout.addRow(self.speed_label, self.speed_combo)

        # Transition-specific fields
        self.from_state_label = QtWidgets.QLabel("From state:")
        self.from_state_label.setStyleSheet("color: #4a2040;")
        self.from_state_combo = QtWidgets.QComboBox()
        for state_key in sorted(available_states):
            self.from_state_combo.addItem(state_key)
        self.from_state_row = self.form_layout.addRow(self.from_state_label, self.from_state_combo)

        self.to_state_label = QtWidgets.QLabel("To state:")
        self.to_state_label.setStyleSheet("color: #4a2040;")
        self.to_state_combo = QtWidgets.QComboBox()
        for state_key in sorted(available_states):
            self.to_state_combo.addItem(state_key)
        self.to_state_row = self.form_layout.addRow(self.to_state_label, self.to_state_combo)

        main_layout.addLayout(self.form_layout)

        # GIF Upload Section
        gif_upload_group = QtWidgets.QGroupBox("GIF File")
        gif_upload_group.setStyleSheet("QGroupBox { color: #e8609c; }")
        gif_upload_layout = QtWidgets.QHBoxLayout(gif_upload_group)

        self.gif_status_label = QtWidgets.QLabel("No GIF selected")
        self.gif_status_label.setStyleSheet("color: #9c6b8a;")
        gif_upload_layout.addWidget(self.gif_status_label)

        self.select_gif_btn = QtWidgets.QPushButton("Select GIF")
        self.select_gif_btn.clicked.connect(self._on_select_gif)
        gif_upload_layout.addWidget(self.select_gif_btn)

        self.clear_pet_gif_btn = QtWidgets.QPushButton("清除 GIF")
        self.clear_pet_gif_btn.clicked.connect(self._on_clear_pet_gif)
        gif_upload_layout.addWidget(self.clear_pet_gif_btn)

        self.manage_gifs_btn = QtWidgets.QPushButton("Manage GIFs...")
        self.manage_gifs_btn.setToolTip("Open gallery to add/remove multiple GIFs")
        self.manage_gifs_btn.clicked.connect(self._on_manage_transition_gifs)
        self.manage_gifs_btn.setVisible(False)  # shown only for transition edit mode
        gif_upload_layout.addWidget(self.manage_gifs_btn)

        main_layout.addWidget(gif_upload_group)

        # GIF Preview
        preview_group = QtWidgets.QGroupBox("GIF Preview")
        preview_group.setStyleSheet("QGroupBox { color: #e8609c; }")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)

        self.preview_label = QtWidgets.QLabel("Select a state to preview")
        self.preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("background-color: #fff5fa; color: #9c6b8a;")
        preview_layout.addWidget(self.preview_label)

        main_layout.addWidget(preview_group)

        # Info label (dynamic based on action type)
        self.info_label = QtWidgets.QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #e8609c; font-size: 11px; padding: 8px;")
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
        """Handle action type change (Movement / Transition / Action)."""
        is_movement = action_type_text == "Movement"
        is_action = action_type_text == "Action"
        is_transition = not is_movement and not is_action

        if is_action:
            self.action_type = "action"
        elif is_movement:
            self.action_type = "movement"
        else:
            self.action_type = "transition"

        # Show/hide movement fields
        self.state_label.setVisible(is_movement)
        self.state_combo.setVisible(is_movement)
        self.direction_label.setVisible(is_movement)
        self.direction_combo.setVisible(is_movement)
        self.speed_label.setVisible(is_movement)
        self.speed_combo.setVisible(is_movement)

        # Show/hide transition fields
        self.from_state_label.setVisible(is_transition)
        self.from_state_combo.setVisible(is_transition)
        self.to_state_label.setVisible(is_transition)
        self.to_state_combo.setVisible(is_transition)

        self.named_action_label.setVisible(is_action)
        self.named_action_combo.setVisible(is_action)
        self._update_gif_buttons()

        # Each builtin keeps its own key and asset binding.
        if is_action:
            self.key_edit.setText(self.named_action_combo.currentData())
            self.key_edit.setEnabled(False)
            self.key_label.setText("Action key:")
        elif not self.is_edit:
            # Re-enable when switching back to movement / transition modes
            # in the new-action flow.
            self.key_edit.setEnabled(True)
            self.key_label.setText("Key (identifier):")

        # Update info label
        if is_movement:
            self.info_label.setText(
                "💡 Movement: LLM determines distance at runtime. Direction can be 'any', 'left', 'right', etc."
            )
        elif is_action:
            self._update_action_info()
        else:
            self.info_label.setText(
                "💡 Transition: Animation plays when changing from one state to another. "
                "Use 'Manage GIFs...' to add multiple GIFs for random selection."
            )

    def _update_gif_buttons(self):
        """Single-file actions pick one GIF; transitions and drag use the gallery."""
        named = self.named_action_combo.currentData() if self.action_type == "action" else None
        is_drag = named == PET_DRAG_ACTION_KEY
        self.manage_gifs_btn.setVisible(self.action_type == "transition" or is_drag)
        self.select_gif_btn.setVisible(not is_drag)
        self.clear_pet_gif_btn.setVisible(named == PET_CLICK_ACTION_KEY)

    def _update_action_info(self):
        action_key = self.named_action_combo.currentData()
        if action_key == PET_CLICK_ACTION_KEY:
            text = "點擊 Doro 本體時播放一次；拖曳不觸發。還沒準備 GIF 也可以保留空白，之後再設定。"
        elif action_key == PET_DRAG_ACTION_KEY:
            text = (
                "拖曳 Doro 時從清單隨機挑一張循環播放，放開後恢復。"
                "用 'Manage GIFs...' 新增或移除；清單空白時保留目前外觀。"
                "圖庫按 OK 立即儲存，外層 Cancel 不會復原圖庫變更。"
            )
        else:
            text = "Doro 幫你點畫面前播放的動作；未綁定時使用站立動畫備援。"
        self.info_label.setText(text)

    def _on_named_action_changed(self, _index: int):
        self.selected_gif_path = None
        self._clear_pet_click_gif = False
        self.key_edit.setText(self.named_action_combo.currentData())
        self._update_gif_buttons()
        self._update_action_info()
        self._load_action_data()

    def _on_clear_pet_gif(self):
        self.selected_gif_path = None
        self._clear_pet_click_gif = True
        self._gif_player.clear()
        self.preview_label.setMovie(None)
        self.preview_label.setText("點擊時保留目前外觀")
        self.gif_status_label.setText("儲存後清除 GIF")

    def _on_state_changed(self, state_key: str):
        """Update GIF preview when state selection changes."""
        self._update_preview(state_key)

    def _on_select_gif(self):
        """Handle GIF file selection."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select sprite file", "", "Animated Images (*.gif *.apng *.webp);;All Files (*.*)"
        )

        if file_path:
            self._clear_pet_click_gif = False
            self.selected_gif_path = Path(file_path)
            self.gif_status_label.setText(self.selected_gif_path.name)
            self.gif_status_label.setStyleSheet("color: #2e7d32;")  # Green color

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

    def _on_manage_transition_gifs(self):
        """Open GIF gallery dialog for transition multi-GIF management."""
        from ..state.gif_gallery_dialog import GifGalleryDialog, apply_gallery_changes

        if self.action_type == "action":
            return self._manage_drag_gifs()

        key = self.key_edit.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Validation", "Please enter a key first.")
            return

        gif_paths = self.service.list_transition_gif_paths(key)
        dialog = GifGalleryDialog(key, key, gif_paths, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            apply_gallery_changes(
                dialog,
                self,
                self.cleanup,
                lambda filename: self.service.remove_transition_gif(key, filename),
                lambda path: self.service.add_transition_gif(key, path),
            )

            # Update status label
            new_count = len(self.service.list_transition_gif_paths(key))
            if new_count > 0:
                self.gif_status_label.setText(f"{new_count} GIF(s)")
                self.gif_status_label.setStyleSheet("color: #2e7d32;")
            else:
                self.gif_status_label.setText("No GIF selected")
                self.gif_status_label.setStyleSheet("color: #9c6b8a;")

    def _manage_drag_gifs(self):
        """Gallery edits to the drag pool apply immediately, like transitions."""
        from ..state.gif_gallery_dialog import GifGalleryDialog, apply_gallery_changes

        if self._action_service is None:
            return
        gif_paths = self._action_service.list_drag_gif_paths()
        dialog = GifGalleryDialog("drag", "Doro 被拖曳", gif_paths, parent=self, allow_empty=True)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            apply_gallery_changes(
                dialog,
                self,
                self.cleanup,
                self._action_service.remove_drag_gif,
                self._action_service.add_drag_gif,
            )
            self._load_action_data()

    def _load_action_data(self) -> None:
        """Populate the dialog with an existing named action's GIF preview."""
        if self._action_service is None:
            return

        # Resolve via the same fallback chain the runtime uses, so what
        # the user sees here is what the next click will actually render.
        action_key = self.named_action_combo.currentData()
        self._gif_player.clear()
        self.preview_label.setMovie(None)
        if action_key == PET_DRAG_ACTION_KEY:
            drag_paths = self._action_service.list_drag_gif_paths()
            if drag_paths:
                self._load_preview_movie(drag_paths[0])
                self.gif_status_label.setText(f"{len(drag_paths)} GIF(s)")
                self.gif_status_label.setStyleSheet("color: #2e7d32;")
            else:
                self.gif_status_label.setText("尚未設定 GIF")
                self.gif_status_label.setStyleSheet("color: #9c6b8a;")
                self.preview_label.setText("拖曳時保留目前外觀；可以之後再設定 GIF。")
            return
        path = self._action_service.resolve_action_gif_path(action_key)
        if path is not None:
            self._load_preview_movie(path)
            self.gif_status_label.setText(f"Current: {path.name}")
            self.gif_status_label.setStyleSheet("color: #2e7d32;")
        else:
            self.gif_status_label.setText("尚未設定 GIF")
            self.preview_label.setText(
                "點擊時保留目前外觀；可以之後再設定 GIF。"
                if action_key == PET_CLICK_ACTION_KEY
                else "No GIF bound — runtime will fall back to a stand pose."
            )

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

        if self.action_type == "action":
            return self._save_action()
        if self.action_type == "movement":
            return self._save_movement()
        return self._save_transition()

    def _save_action(self):
        """Persist the user's GIF choice for a named action.

        Selecting no new GIF keeps the existing binding. Pet-click gestures
        can be explicitly cleared, returning to the current-sprite behavior.
        """
        if self._action_service is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Save",
                "Action editor is not available in this dialog. "
                "Wire the ActionService through and try again.",
            )
            return

        action_key = self.named_action_combo.currentData()
        if action_key == PET_DRAG_ACTION_KEY:
            # The drag pool is edited through the gallery, which saves immediately.
            self.accept()
            return
        if action_key == PET_CLICK_ACTION_KEY and self._clear_pet_click_gif:
            if not self._action_service.unbind_pet_click_gif():
                QtWidgets.QMessageBox.warning(self, "Save", "Failed to clear the GIF.")
                return
            self.accept()
            return

        if self.selected_gif_path is None:
            # Missing artwork is allowed; keep the current binding.
            self.accept()
            return

        bind = (
            self._action_service.bind_pet_click_gif
            if action_key == PET_CLICK_ACTION_KEY
            else self._action_service.bind_click_gif
        )
        if not bind(self.selected_gif_path):
            QtWidgets.QMessageBox.warning(
                self,
                "Save",
                "Failed to bind the GIF to the click action.",
            )
            return
        self.accept()

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
        if self.selected_gif_path and not self.service.set_gif(state_key, self.selected_gif_path):
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

        # Upload custom transition GIF if selected (uses multi-GIF service)
        transition_gif_id = None
        if self.selected_gif_path:
            if self.service.add_transition_gif(key, self.selected_gif_path):
                # Sanitize key for a gif_id marker
                safe_key = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
                transition_gif_id = f"{safe_key}.gif"
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Failed to upload GIF. Transition will be saved without custom GIF.",
                )

        # For edits, preserve existing gif_id if we didn't upload a new one
        if not transition_gif_id and self.is_edit:
            existing = self.service.get_transition(key)
            if existing:
                transition_gif_id = existing.transition_gif_id

        # Create Transition
        transition = Transition(
            key=key,
            from_state=from_state,
            to_state=to_state,
            transition_gif_id=transition_gif_id,
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

    def cleanup(self) -> None:
        """Release preview handles on OK, Cancel, window close and before file edits."""
        self.preview_label.setMovie(None)
        self._gif_player.clear()

    def done(self, result: int) -> None:
        self.cleanup()
        super().done(result)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.cleanup()
        super().closeEvent(event)
