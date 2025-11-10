"""State and GIF management for the Doro application."""

from __future__ import annotations

import copy
import json
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from .models import MoveStateSettings, StateSettings

if TYPE_CHECKING:
    from .window import DoroWindow


class StateManager:
    """Encapsulates state initialization, storage, and GIF management."""

    def __init__(self, window: DoroWindow):
        self._window = window
        self._direction_splitter = re.compile(r"[|,;/\s]+")

    def init_states(self):
        """Create default states and load user overrides."""
        w = self._window
        w._state_defs = {
            "idle": StateSettings(
                label="Idle",
            ),
        }
        default_gif_path = str(w._default_idle_gif) if w._default_idle_gif.is_file() else None
        if default_gif_path:
            for state in w._state_defs.values():
                if not state.gif_path:
                    state.gif_path = default_gif_path
        w._protected_state_keys = set(w._state_defs.keys())
        self.ensure_walking_state_available()
        self._load_custom_states()
        self.set_state("idle")
        self.write_state_list()

    def _load_custom_states(self):
        w = self._window
        if not w._state_config_path.is_file():
            return
        try:
            raw = w._state_config_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            normalized = (key or "").strip().lower()
            if normalized in w._movement_only_state_keys:
                continue
            settings = self.state_settings_from_dict(key, value)
            w._state_defs[key] = settings

    def init_move_states(self):
        """Ensure movement-specific states exist."""
        w = self._window
        w._move_state_defs.clear()
        step_default = max(12, int(w._movement_step_px))
        default_distance = float(step_default)
        default_speed = "med"
        self.register_move_state(
            w._default_move_state_key,
            state_key=w._default_move_state_key,
            default_distance=default_distance,
            default_speed=default_speed,
        )
        self.ensure_walking_state_available()

    def is_movement_only_state(self, key: str) -> bool:
        """Return True if the key is reserved for movement-only animations."""
        return key.strip().lower() in self._window._movement_only_state_keys

    def visible_state_keys(self) -> list[str]:
        """List states that are selectable in the UI."""
        w = self._window
        return [key for key in w._state_defs if not self.is_movement_only_state(key)]

    def register_move_state(
        self,
        key: str,
        *,
        state_key: str,
        direction: str | None = None,
        default_distance: float | None = None,
        default_speed: str | None = None,
    ) -> bool:
        w = self._window
        normalized = (key or "").strip().lower()
        if not normalized:
            return False
        existing = w._move_state_defs.get(normalized)
        distance = (
            default_distance
            if default_distance is not None
            else (existing.default_distance if existing else None)
        )
        speed = (
            default_speed
            if default_speed is not None
            else (existing.default_speed if existing else None)
        )
        direction_value = (
            existing.direction if direction is None and existing is not None else self._normalize_direction_value(direction)
        )
        state_key_clean = (state_key or normalized).strip() or normalized
        if state_key_clean:
            w._movement_only_state_keys.add(state_key_clean.lower())
        new_settings = MoveStateSettings(
            state_key=state_key_clean,
            direction=direction_value,
            default_distance=distance,
            default_speed=speed,
        )
        changed = existing != new_settings
        w._move_state_defs[normalized] = new_settings
        return changed

    def unregister_move_state(self, key: str) -> bool:
        normalized = (key or "").strip().lower()
        if not normalized:
            return False
        w = self._window
        settings = w._move_state_defs.pop(normalized, None)
        if not settings:
            return False
        w._movement_only_state_keys.discard(settings.state_key.lower())
        return True

    def _normalize_direction_value(self, value: str | None) -> str:
        tokens = self._split_direction_tokens(value)
        if not tokens:
            return "any"
        unique: list[str] = []
        for token in tokens:
            if token not in unique:
                unique.append(token)
        return "|".join(unique)

    def _split_direction_tokens(self, value: str | None) -> list[str]:
        if not value:
            return []
        raw = (
            value
            if isinstance(value, str)
            else str(value)
        )
        tokens = [
            token.strip().lower()
            for token in self._direction_splitter.split(raw)
            if token.strip()
        ]
        return tokens

    def resolve_move_state(self, key: str | None) -> tuple[Optional[str], Optional[MoveStateSettings]]:
        w = self._window
        if not key:
            return (None, None)
        normalized = key.strip().lower()
        if not normalized:
            return (None, None)
        settings = w._move_state_defs.get(normalized)
        if settings is None:
            return (None, None)
        return (normalized, settings)

    def restore_state_from_config(self):
        """Reload last selected state and associated GIFs."""
        w = self._window
        state_key = w._config.value("current_state", "idle")
        if state_key not in w._state_defs:
            state_key = "idle"

        for key, state in w._state_defs.items():
            saved_path = w._config.value(f"state/{key}/gif_path", "", str)
            if saved_path:
                saved_file = Path(saved_path)
                if saved_file.is_file():
                    state.gif_path = saved_path
                    continue
            state_file = self.state_storage_path_for_key(key)
            if state_file.is_file():
                state.gif_path = str(state_file)
            elif w._default_idle_gif.is_file():
                state.gif_path = str(w._default_idle_gif)
            else:
                state.gif_path = None
            self.ensure_local_gif_for_state(key)

        self.set_state(state_key)

    def set_state(self, key: str):
        w = self._window
        if key not in w._state_defs:
            return
        self.ensure_local_gif_for_state(key)
        self._update_state_variants(key)
        if w._current_state_key and w._state_settings:
            w._state_defs[w._current_state_key] = copy.deepcopy(w._state_settings)
        w._current_state_key = key
        w._active_gif_path = None
        w._state_settings = copy.deepcopy(w._state_defs[key])
        self._select_state_gif_variant(key)
        w._apply_state_settings()
        w.update()
        w._persist_current_state()

    def reset_state_overrides(self):
        w = self._window
        if not w._current_state_key:
            return
        w._active_gif_path = None
        w._state_settings = copy.deepcopy(w._state_defs[w._current_state_key])
        w._apply_state_settings()
        w.update()
        w._persist_current_state()

    def load_state_gif(self):
        if not self._window._state_defs:
            return
        self.show_state_gif_manager()

    def set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        w = self._window
        if key not in w._state_defs:
            return False
        if not Path(source_path).is_file():
            QtWidgets.QMessageBox.warning(w, "Load GIF", "The selected file does not exist.")
            return False
        dest_path = self._state_storage_path_for_key(key)
        try:
            shutil.copy2(source_path, dest_path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                w,
                "Load GIF",
                f"Failed to copy GIF to internal storage:\n{exc}",
            )
            return False
        if key == w._current_state_key and w._state_settings is not None:
            w._state_settings.gif_path = str(dest_path)
            w._active_gif_path = None
            w._apply_state_settings()
            if w._gif_movie is None:
                QtWidgets.QMessageBox.warning(
                    w,
                    "Load GIF",
                    "Failed to load the selected GIF.",
                )
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except OSError:
                        pass
                if w._default_idle_gif.is_file():
                    w._state_settings.gif_path = str(w._default_idle_gif)
                else:
                    w._state_settings.gif_path = None
                try:
                    self.save_state_settings()
                    w._apply_state_settings()
                finally:
                    w.update()
                return False
            self.save_state_settings()
            self._update_state_variants(key)
        else:
            self._update_state_variants(key)
        return True

    def add_state_gif_variant_from_path(self, key: str, source_path: str) -> bool:
        w = self._window
        if key not in w._state_defs:
            return False
        src = Path(source_path)
        if not src.is_file():
            QtWidgets.QMessageBox.warning(w, "Add GIF variant", "The selected file does not exist.")
            return False
        dest_dir = self.state_variants_dir_for_key(key)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                w,
                "Add GIF variant",
                f"Failed to prepare variant folder:\n{exc}",
            )
            return False
        dest_path = dest_dir / src.name
        if dest_path.suffix.lower() != ".gif":
            dest_path = dest_path.with_suffix(".gif")
        counter = 1
        original_stem = dest_path.stem
        while dest_path.exists():
            dest_path = dest_dir / f"{original_stem}_{counter}.gif"
            counter += 1
        try:
            shutil.copy2(src, dest_path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                w,
                "Add GIF variant",
                f"Failed to copy GIF variant:\n{exc}",
            )
            return False
        movie = QtGui.QMovie(str(dest_path))
        if not movie.isValid():
            QtWidgets.QMessageBox.warning(
                w,
                "Add GIF variant",
                "Failed to load the selected GIF variant.",
            )
            try:
                dest_path.unlink()
            except OSError:
                pass
            return False
        self._update_state_variants(key)
        if key == w._current_state_key and w._state_settings is not None:
            w._state_settings.gif_variants = copy.deepcopy(w._state_defs[key].gif_variants)
            self._select_state_gif_variant(key)
            w._apply_state_settings()
            w.update()
        self.write_state_list()
        return True

    def remove_state_gif_variant(
        self,
        key: str,
        variant_path: str,
        *,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        w = self._window
        settings = w._state_defs.get(key)
        if settings is None:
            return False
        try:
            path_obj = Path(variant_path)
        except (TypeError, ValueError):
            return False
        variants_dir = self.state_variants_dir_for_key(key)
        try:
            path_obj.relative_to(variants_dir)
        except ValueError:
            return False
        if not path_obj.exists():
            return False
        try:
            path_obj.unlink()
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                parent or w,
                "Remove GIF variant",
                f"Failed to delete variant:\n{exc}",
            )
            return False
        try:
            if variants_dir.is_dir():
                next(variants_dir.iterdir())
        except StopIteration:
            try:
                variants_dir.rmdir()
            except OSError:
                pass
        self._update_state_variants(key)
        if key == w._current_state_key and w._state_settings is not None:
            w._state_settings.gif_variants = copy.deepcopy(w._state_defs[key].gif_variants)

            def _normalize(path_str: str | None) -> str | None:
                if not path_str:
                    return None
                try:
                    candidate = Path(path_str)
                except (TypeError, ValueError):
                    return path_str
                try:
                    return str(candidate.resolve())
                except OSError:
                    return str(candidate)

            active_removed = False
            active_norm = _normalize(w._active_gif_path)
            removed_norm = _normalize(variant_path)
            if active_norm and removed_norm and active_norm == removed_norm:
                w._active_gif_path = None
                active_removed = True

            main_norm = _normalize(w._state_settings.gif_path)
            variant_norms = {_normalize(p) for p in w._state_settings.gif_variants}
            needs_variant = active_removed or main_norm is None or main_norm not in variant_norms
            if needs_variant:
                self._select_state_gif_variant(key)
                w._apply_state_settings()
                w.update()
        self.write_state_list()
        return True

    def clear_state_gif(self, key: str) -> bool:
        w = self._window
        settings = w._state_defs.get(key)
        if settings is None:
            return False
        stored_path = Path(settings.gif_path or "")
        if stored_path.is_file():
            try:
                stored_path.relative_to(w._state_storage_dir)
            except ValueError:
                pass
            else:
                if stored_path != w._default_idle_gif:
                    try:
                        stored_path.unlink()
                    except OSError:
                        pass
        settings.gif_path = None
        self._update_state_variants(key)
        if key == w._current_state_key and w._state_settings is not None:
            w._state_settings.gif_path = str(w._default_idle_gif) if w._default_idle_gif.is_file() else None
            w._apply_state_settings()
            self.save_state_settings()
        self.write_state_list()
        return True

    def show_state_gif_manager(self):
        w = self._window
        dialog = QtWidgets.QDialog(w)
        dialog.setWindowTitle("State GIFs")
        dialog.setMinimumWidth(680)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        table = QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["State", "Preview", "GIF Path", "Actions"])
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(table)

        def repopulate():
            table.setRowCount(0)
            for row, key in enumerate(sorted(self.visible_state_keys())):
                table.insertRow(row)
                state = w._state_defs[key]
                label = state.label or key
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"{label}\n({key})"))
                gif_path = state.gif_path or "(no GIF)"
                table.setItem(row, 2, QtWidgets.QTableWidgetItem(gif_path))
                preview_label = QtWidgets.QLabel()
                preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                preview_label.setMinimumSize(114, 114)
                if state.gif_path and Path(state.gif_path).is_file():
                    movie = QtGui.QMovie(state.gif_path)
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(96, 96))
                        preview_label.setMovie(movie)
                        movie.start()
                table.setCellWidget(row, 1, preview_label)
                btn = QtWidgets.QPushButton("Set GIF")
                btn.clicked.connect(lambda _chk=False, s=key: self._prompt_set_state_gif(s, dialog))
                remove_btn = QtWidgets.QPushButton("Clear")
                remove_btn.clicked.connect(lambda _chk=False, s=key: self.clear_state_gif(s))
                btn_layout = QtWidgets.QHBoxLayout()
                btn_layout.addWidget(btn)
                btn_layout.addWidget(remove_btn)
                container = QtWidgets.QWidget()
                container.setLayout(btn_layout)
                table.setCellWidget(row, 3, container)

        repopulate()
        dialog.exec()

    def _prompt_set_state_gif(self, state_key: str, parent: QtWidgets.QWidget):
        w = self._window
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent,
            f"Select GIF for '{state_key}'",
            str(w._state_storage_dir),
            "GIF files (*.gif)",
        )
        if not file_path:
            return
        if self.set_state_gif_from_path(state_key, file_path):
            self.write_state_list()

    def show_state_gif_collection(self, state_key: str, *, parent: QtWidgets.QWidget | None = None):
        w = self._window
        if state_key not in w._state_defs:
            return
        self._update_state_variants(state_key)

        dialog_parent = parent or w
        dialog = QtWidgets.QDialog(dialog_parent)
        dialog.setWindowTitle(f"GIF variants · {state_key}")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet("#variantDialog { background-color: #080f1d; border-radius: 20px; }")
        dialog.setObjectName("variantDialog")

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        info_label = QtWidgets.QLabel(
            "Manage the primary animation and additional variants. Doro will randomly pick one when this state is active."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #a5b4fc; font-size: 11px;")
        layout.addWidget(info_label)

        list_widget = QtWidgets.QListWidget(dialog)
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        list_widget.setStyleSheet(
            "QListWidget { background-color: rgba(15, 23, 42, 0.55); border-radius: 12px; padding: 8px; }"
            "QListWidget::item { color: #e2e8f0; padding: 6px 10px; border-radius: 8px; }"
            "QListWidget::item:selected { background-color: rgba(129, 140, 248, 0.35); }"
        )
        layout.addWidget(list_widget, stretch=1)

        preview_label = QtWidgets.QLabel()
        preview_label.setFixedHeight(180)
        preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet(
            "background: rgba(15, 23, 42, 0.65); border-radius: 14px; color: #93c5fd; border: 1px solid rgba(148, 163, 184, 0.35);"
        )
        layout.addWidget(preview_label)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(12)
        layout.addLayout(button_row)

        add_button = QtWidgets.QPushButton("Add variant")
        add_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        add_button.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38bdf8, stop:1 #6366f1);"
            "color: #04070f; font-weight: 600; border-radius: 12px; padding: 8px 18px; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #67e8f9, stop:1 #818cf8); }"
        )
        button_row.addWidget(add_button)

        set_main_button = QtWidgets.QPushButton("Set as main")
        set_main_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        set_main_button.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fbbf24, stop:1 #fb7185);"
            "color: #05070f; font-weight: 600; border-radius: 12px; padding: 8px 18px; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fde047, stop:1 #fda4af); }"
            "QPushButton:disabled { background: rgba(148,163,184,0.25); color: rgba(245,245,255,0.55); }"
        )
        button_row.addWidget(set_main_button)

        remove_button = QtWidgets.QPushButton("Remove variant")
        remove_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        remove_button.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f87171, stop:1 #fb7185);"
            "color: #05070f; font-weight: 600; border-radius: 12px; padding: 8px 18px; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fca5a5, stop:1 #fda4af); }"
            "QPushButton:disabled { background: rgba(148,163,184,0.25); color: rgba(245,245,255,0.55); }"
        )
        button_row.addWidget(remove_button)

        close_button = QtWidgets.QPushButton("Close")
        close_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        close_button.setStyleSheet(
            "QPushButton { background: rgba(148,163,184,0.25); color: #e2e8f0; border-radius: 12px; padding: 8px 18px; }"
            "QPushButton:hover { background: rgba(148,163,184,0.4); }"
        )
        button_row.addWidget(close_button)

        preview_movie: list[QtGui.QMovie | None] = [None]

        def stop_preview():
            movie = preview_movie[0]
            if movie:
                movie.stop()
            preview_movie[0] = None
            preview_label.setMovie(None)

        def show_preview(path: str | None):
            stop_preview()
            if not path:
                preview_label.setText("No GIF selected")
                return
            movie = QtGui.QMovie(path)
            if not movie.isValid():
                preview_label.setText("Invalid GIF")
                return
            preview_label.setMovie(movie)
            preview_movie[0] = movie
            movie.start()

        def repopulate():
            list_widget.clear()
            settings = w._state_defs[state_key]
            entries = []
            if settings.gif_path:
                entries.append(("Primary GIF", settings.gif_path))
            for idx, path in enumerate(settings.gif_variants, start=1):
                entries.append((f"Variant {idx}", path))
            for label, path in entries:
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
                list_widget.addItem(item)
            if entries:
                list_widget.setCurrentRow(0)
                show_preview(entries[0][1])
            else:
                show_preview(None)

        def current_path() -> str | None:
            item = list_widget.currentItem()
            if not item:
                return None
            return item.data(QtCore.Qt.ItemDataRole.UserRole)

        def on_add_variant():
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog,
                f"Add GIF variant for '{state_key}'",
                str(w._state_storage_dir),
                "GIF files (*.gif)",
            )
            if not file_path:
                return
            if self.add_state_gif_variant_from_path(state_key, file_path):
                self._update_state_variants(state_key)
                repopulate()

        def on_set_main():
            path = current_path()
            if not path:
                return
            settings = w._state_defs[state_key]
            settings.gif_path = path
            if state_key == w._current_state_key and w._state_settings is not None:
                w._state_settings.gif_path = path
                w._apply_state_settings()
            self.save_state_settings()
            repopulate()

        def on_remove_variant():
            path = current_path()
            if not path or path == w._state_defs[state_key].gif_path:
                QtWidgets.QMessageBox.information(dialog, "Remove variant", "Select a variant entry to remove.")
                return
            self.remove_state_gif_variant(state_key, path, parent=dialog)
            repopulate()

        list_widget.itemSelectionChanged.connect(lambda: show_preview(current_path()))
        add_button.clicked.connect(on_add_variant)
        set_main_button.clicked.connect(on_set_main)
        remove_button.clicked.connect(on_remove_variant)
        close_button.clicked.connect(dialog.accept)

        repopulate()
        dialog.finished.connect(lambda _code: stop_preview())
        dialog.exec()

    def add_state(self) -> Optional[str]:
        w = self._window
        key, ok = QtWidgets.QInputDialog.getText(
            w,
            "Add new state",
            "Unique state key:",
        )
        if not ok:
            return None
        key = key.strip()
        if not key:
            return None
        normalized_key = key.lower()
        if normalized_key in w._movement_only_state_keys:
            QtWidgets.QMessageBox.warning(
                w,
                "Add state",
                "This key is reserved for movement animations.",
            )
            return None
        if key in w._state_defs:
            QtWidgets.QMessageBox.warning(
                w,
                "Add state",
                "A state with this key already exists.",
            )
            return None

        default_label = key.capitalize()
        label, ok = QtWidgets.QInputDialog.getText(
            w,
            "Add new state",
            "Display name:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            default_label,
        )
        if not ok:
            return None
        label = label.strip() or default_label

        base_settings = (
            copy.deepcopy(w._state_settings)
            if w._state_settings is not None
            else StateSettings(label=label)
        )
        base_settings.label = label
        base_settings.name_tag = base_settings.name_tag or label
        w._state_defs[key] = base_settings
        self.ensure_local_gif_for_state(key)
        self.set_state(key)
        self.persist_state_definitions()
        return key

    def remove_state_by_key(
        self,
        key: str,
        *,
        confirm: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        w = self._window
        if not key or key not in w._state_defs:
            return False
        if key in w._protected_state_keys:
            return False

        target_parent = parent or w
        state_label = w._state_defs[key].label or key
        if confirm:
            reply = QtWidgets.QMessageBox.question(
                target_parent,
                "Remove state",
                f"Remove state '{state_label}'?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return False

        settings = w._state_defs[key]
        stored_path = Path(settings.gif_path or "")
        if stored_path.is_file():
            try:
                stored_path.relative_to(w._state_storage_dir)
            except ValueError:
                pass
            else:
                if stored_path != w._default_idle_gif:
                    try:
                        stored_path.unlink()
                    except OSError:
                        pass
        variant_dir = self._state_variants_dir_for_key(key)
        if variant_dir.is_dir():
            try:
                shutil.rmtree(variant_dir)
            except OSError:
                pass
        w._config.remove(f"state/{key}/gif_path")

        del w._state_defs[key]
        if w._current_state_key == key:
            visible_keys = self.visible_state_keys()
            if visible_keys:
                next_key = "idle" if "idle" in visible_keys else visible_keys[0]
                self.set_state(next_key)
            else:
                w._current_state_key = ""
                w._state_settings = None
                w.update()
                w._config.setValue("current_state", "")
        else:
            w._persist_current_state()

        self.persist_state_definitions()
        self.write_state_list()
        return True

    def remove_current_state(self):
        w = self._window
        if not w._current_state_key:
            return
        self.remove_state_by_key(w._current_state_key)

    def write_state_list(self):
        w = self._window
        if not w._state_defs:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的狀態為:"]
        transition_keys = sorted(self.visible_state_keys())
        for key in transition_keys:
            state = w._state_defs[key]
            label = state.label or key
            gif_hint = state.gif_path or "(no GIF)"
            variants_count = 0
            if state.gif_variants:
                unique_variants = []
                for path in state.gif_variants:
                    if path and path not in unique_variants:
                        unique_variants.append(path)
                variants_count = max(0, len(unique_variants) - (1 if state.gif_path else 0))
            if variants_count > 0:
                gif_hint = f"{gif_hint} (+{variants_count} variants)"
            action_kind, directions = self.action_profile_for_state(key)
            if action_kind == "movement":
                dir_text = ", ".join(directions) if directions else "unspecified"
                meta = f"type: movement ({dir_text})"
            else:
                meta = "type: transition"
            lines.append(f"- ({key}) {label} | {meta} | GIF: {gif_hint}")

        movement_keys = self._movement_state_keys()
        if movement_keys:
            lines.append("")
            lines.append("移動專用狀態:")
            for key in movement_keys:
                state = w._state_defs.get(key)
                if not state:
                    continue
                label = state.label or key
                gif_hint = state.gif_path or "(no GIF)"
                directions = self._split_direction_tokens(self._movement_direction_for_state(key))
                dir_text = ", ".join(directions) if directions else "unspecified"
                lines.append(f"- ({key}) {label} | type: movement ({dir_text}) | GIF: {gif_hint}")
        output = "\n".join(lines) + "\n"
        w._state_list_text = output.strip()
        try:
            w._state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    def action_profile_for_state(self, key: str) -> tuple[str, list[str]]:
        if not key:
            return ("transition", [])
        movement_only = getattr(self._window, "_movement_only_state_keys", set())
        if key in movement_only:
            return ("movement", self._split_direction_tokens(self._movement_direction_for_state(key)))
        for move_settings in self._window._move_state_defs.values():
            if move_settings.state_key == key:
                return ("movement", self._split_direction_tokens(move_settings.direction))
        return ("transition", [])

    def _movement_state_keys(self) -> list[str]:
        keys: set[str] = set()
        movement_only = getattr(self._window, "_movement_only_state_keys", set())
        keys.update(key for key in movement_only if key in self._window._state_defs)
        for move_settings in self._window._move_state_defs.values():
            if move_settings.state_key in self._window._state_defs:
                keys.add(move_settings.state_key)
        return sorted(keys)

    def _list_action_files(self) -> list[dict]:
        results: list[dict] = []
        move_dir = getattr(self._window, "_move_storage_dir", None)
        if move_dir and Path(move_dir).is_dir():
            for path in sorted(Path(move_dir).glob("*.gif")):
                results.append(
                    {
                        "key": path.stem,
                        "type": "movement",
                        "path": str(path),
                        "direction": self._split_direction_tokens(self._movement_direction_for_state(path.stem)),
                    }
                )
        transition_dir = getattr(self._window, "_transition_action_dir", None)
        if transition_dir and Path(transition_dir).is_dir():
            for path in sorted(Path(transition_dir).glob("*.gif")):
                results.append(
                    {
                        "key": path.stem,
                        "type": "transition",
                        "path": str(path),
                        "direction": [],
                    }
                )
        return results

    def _movement_direction_for_state(self, key: str) -> str | None:
        move_state_defs = getattr(self._window, "_move_state_defs", {})
        for move_settings in move_state_defs.values():
            if move_settings.state_key == key:
                direction = (move_settings.direction or "").strip().lower()
                return direction or None
        return None

    def pick_random_state_for_direction(self, slug: str | None) -> Optional[str]:
        if not slug:
            return None
        slug = slug.strip().lower()
        if not slug:
            return None
        move_state_defs = getattr(self._window, "_move_state_defs", {})
        matches: list[str] = []
        for settings in move_state_defs.values():
            tokens = self._split_direction_tokens(settings.direction)
            if "any" in tokens or slug in tokens:
                if settings.state_key in self._window._state_defs:
                    matches.append(settings.state_key)
        if matches:
            return random.choice(matches)
        return None

    def write_move_state_list(self):
        w = self._window
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的移動狀態為:"]
        if not w._move_state_defs:
            lines.append("- (none) 無移動專用狀態")
        else:
            for key in sorted(w._move_state_defs.keys()):
                move_settings = w._move_state_defs[key]
                direction_tokens = self._split_direction_tokens(move_settings.direction)
                direction = ", ".join(direction_tokens) if direction_tokens else "any"
                state_key = move_settings.state_key
                state_settings = w._state_defs.get(state_key)
                label = state_settings.label if state_settings else state_key
                gif_hint = (
                    state_settings.gif_path
                    if state_settings and state_settings.gif_path
                    else "(no GIF)"
                )
                lines.append(
                    f"- ({key}) {label} | direction: {direction} | state: {state_key} | GIF: {gif_hint}"
                )
        output = "\n".join(lines) + "\n"
        w._move_state_list_text = output.strip()
        try:
            w._move_state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    def save_state_settings(self):
        w = self._window
        if not w._current_state_key or w._state_settings is None:
            return
        w._state_defs[w._current_state_key] = copy.deepcopy(w._state_settings)
        w._persist_current_state()
        self.persist_state_definitions()

    def state_settings_to_dict(self, settings: StateSettings) -> dict:
        data = copy.deepcopy(settings.__dict__)
        data.pop("gif_path", None)
        data.pop("gif_variants", None)
        return data

    def state_settings_from_dict(self, key: str, data: dict) -> StateSettings:
        fields = {field.name for field in StateSettings.__dataclass_fields__.values()}
        clean = {
            k: v
            for k, v in data.items()
            if k in fields and k not in {"gif_path", "gif_variants"}
        }
        if "label" not in clean or not str(clean["label"]).strip():
            clean["label"] = key.capitalize()
        return StateSettings(**clean)

    def persist_state_definitions(self):
        w = self._window
        custom_states = {
            key: self.state_settings_to_dict(settings)
            for key, settings in w._state_defs.items()
            if key not in w._protected_state_keys
        }
        try:
            if custom_states:
                w._state_config_path.parent.mkdir(parents=True, exist_ok=True)
                w._state_config_path.write_text(
                    json.dumps(custom_states, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                if w._state_config_path.exists():
                    w._state_config_path.unlink()
        except OSError:
            pass

    def state_storage_path_for_key(self, key: str) -> Path:
        return self._window._state_storage_dir / f"{self._state_storage_token(key)}.gif"

    def state_variants_dir_for_key(self, key: str) -> Path:
        return self._window._state_storage_dir / f"{self._state_storage_token(key)}_variants"

    def move_storage_path_for_key(self, key: str) -> Path:
        return self._window._move_storage_dir / f"{self._state_storage_token(key)}.gif"

    # Compatibility helpers for existing window methods
    def _state_storage_path_for_key(self, key: str) -> Path:
        return self.state_storage_path_for_key(key)

    def _state_variants_dir_for_key(self, key: str) -> Path:
        return self.state_variants_dir_for_key(key)

    def _move_storage_path_for_key(self, key: str) -> Path:
        return self.move_storage_path_for_key(key)

    def _state_storage_token(self, key: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        return safe or "state"

    def show_move_gif_manager(self):
        w = self._window
        self.ensure_walking_state_available()

        dialog = QtWidgets.QDialog(w)
        dialog.setWindowTitle("Action GIFs")
        dialog.setObjectName("doroActionDialog")
        dialog.setMinimumWidth(720)
        dialog.setStyleSheet("#doroActionDialog { background-color: #060b15; border-radius: 20px; }")

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)
        table = QtWidgets.QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Key", "Type", "Direction", "State", "Preview", "Manage"])
        header = table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(4, 160)
        table.setColumnWidth(5, 180)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(True)
        layout.addWidget(table)

        button_bar = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("Add action")
        button_bar.addWidget(add_button)
        button_bar.addStretch()
        layout.addLayout(button_bar)

        preview_size = QtCore.QSize(114, 114)

        def repopulate(select_key: str | None = None):
            table.setRowCount(0)
            entries = self._list_action_files()
            for row_index, entry in enumerate(entries):
                key = entry["key"]
                table.insertRow(row_index)
                table.setRowHeight(row_index, preview_size.height() + 12)
                normalized = key.strip().lower()
                move_settings = w._move_state_defs.get(normalized)
                action_kind = entry["type"]
                direction_tokens = entry["direction"]
                if not direction_tokens and move_settings:
                    direction_tokens = self._split_direction_tokens(move_settings.direction)
                direction_text = ", ".join(direction_tokens) if direction_tokens else "-"
                state_key = move_settings.state_key if move_settings else key
                state_settings = w._state_defs.get(state_key)
                state_label = state_settings.label if state_settings and state_settings.label else state_key

                key_item = QtWidgets.QTableWidgetItem(key)
                key_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row_index, 0, key_item)

                type_item = QtWidgets.QTableWidgetItem(
                    "Movement" if action_kind == "movement" else "Transition"
                )
                type_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row_index, 1, type_item)

                dir_item = QtWidgets.QTableWidgetItem(direction_text)
                dir_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row_index, 2, dir_item)

                state_item = QtWidgets.QTableWidgetItem(state_label)
                state_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row_index, 3, state_item)

                preview_label = QtWidgets.QLabel()
                preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                preview_label.setMinimumSize(preview_size)
                gif_path: str | None = entry["path"]
                movie = QtGui.QMovie(gif_path)
                if movie.isValid():
                    movie.setScaledSize(preview_size - QtCore.QSize(18, 18))
                    preview_label.setMovie(movie)
                    movie.start()
                table.setCellWidget(row_index, 4, preview_label)

                manage_widget = QtWidgets.QWidget()
                manage_layout = QtWidgets.QHBoxLayout(manage_widget)
                manage_layout.setContentsMargins(0, 0, 0, 0)
                edit_btn = QtWidgets.QPushButton("Edit")
                edit_btn.clicked.connect(
                    lambda _chk=False, action_key=key, action_type=action_kind, gif_path=gif_path: self._prompt_edit_action(
                        action_key,
                        dialog,
                        repopulate,
                        default_type=action_type,
                        action_path=gif_path,
                    )
                )
                manage_layout.addWidget(edit_btn)
                if action_kind == "movement":
                    gif_btn = QtWidgets.QPushButton("Set GIF")
                    gif_btn.clicked.connect(
                        lambda _chk=False, action_key=key: self._set_gif_and_refresh(action_key, dialog, repopulate)
                    )
                    manage_layout.addWidget(gif_btn)
                manage_layout.addStretch()
                table.setCellWidget(row_index, 5, manage_widget)

                if select_key and select_key == key:
                    table.selectRow(row_index)

        repopulate()
        add_button.clicked.connect(lambda _chk=False: self._prompt_edit_action(None, dialog, repopulate))
        dialog.exec()

    def _set_gif_and_refresh(
        self,
        action_key: str,
        parent: QtWidgets.QWidget,
        refresh: Callable[[str | None], None] | None = None,
    ):
        self._prompt_move_gif(action_key, parent)
        if refresh:
            refresh(action_key)

    def _prompt_move_gif(self, action_key: str, parent: QtWidgets.QWidget):
        w = self._window
        dest = self.move_storage_path_for_key(action_key)
        start_dir = dest.parent if dest.parent.is_dir() else w._move_storage_dir
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent,
            f"Select GIF for '{action_key}'",
            str(start_dir),
            "GIF files (*.gif)",
        )
        if not file_path:
            return
        src = Path(file_path)
        if not src.is_file():
            QtWidgets.QMessageBox.warning(parent, "Assign action GIF", "The selected file does not exist.")
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            same_path = dest.is_file() and src.resolve() == dest.resolve()
        except OSError:
            same_path = False
        if not same_path:
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                QtWidgets.QMessageBox.warning(
                    parent,
                    "Assign action GIF",
                    f"Failed to copy GIF into action storage:\n{exc}",
                )
                return
        if not dest.is_file():
            QtWidgets.QMessageBox.warning(
                parent,
                "Assign action GIF",
                "Failed to prepare the action GIF in the move folder.",
            )
            return
        self.apply_move_gif_update(action_key)

    def _prompt_edit_action(
        self,
        action_key: str | None,
        parent: QtWidgets.QWidget | None = None,
        refresh: Callable[[str | None], None] | None = None,
        *,
        default_type: str | None = None,
        action_path: str | None = None,
    ):
        w = self._window
        dialog = QtWidgets.QDialog(parent or w)
        dialog.setWindowTitle("Edit action properties" if action_key else "Add action")
        dialog.setMinimumWidth(420)

        form = QtWidgets.QFormLayout(dialog)
        key_edit = QtWidgets.QLineEdit()
        if action_key:
            key_edit.setText(action_key)
            key_edit.setEnabled(False)
        form.addRow("Action key:", key_edit)

        state_combo = QtWidgets.QComboBox()
        state_combo.setEditable(True)
        for state_key in sorted(w._state_defs.keys()):
            state_combo.addItem(state_key)

        type_combo = QtWidgets.QComboBox()
        type_combo.addItem("Movement", "movement")
        type_combo.addItem("Transition", "transition")

        direction_list = QtWidgets.QListWidget()
        direction_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        direction_items: list[QtWidgets.QListWidgetItem] = []
        direction_values = [
            ("None", None),
            ("Any", "any"),
            ("Left", "left"),
            ("Right", "right"),
            ("Up", "up"),
            ("Down", "down"),
            ("Up-Left", "up_left"),
            ("Up-Right", "up_right"),
            ("Down-Left", "down_left"),
            ("Down-Right", "down_right"),
        ]
        direction_item_map: dict[str | None, QtWidgets.QListWidgetItem] = {}
        direction_guard = {"block": False}

        for label, value in direction_values:
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            direction_list.addItem(item)
            direction_items.append(item)
            direction_item_map[value] = item

        speed_combo = QtWidgets.QComboBox()
        speed_combo.addItem("Slow", "slow")
        speed_combo.addItem("Medium", "med")
        speed_combo.addItem("Fast", "fast")

        form.addRow("State key:", state_combo)
        form.addRow("Type:", type_combo)
        form.addRow("Direction:", direction_list)
        form.addRow("Speed:", speed_combo)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(button_box)

        normalized = action_key.lower() if action_key else ""
        existing_move = w._move_state_defs.get(normalized) if action_key else None
        if action_key:
            state_combo.setEditText(existing_move.state_key if existing_move else action_key)
        else:
            key_edit.setPlaceholderText("e.g. walking_left")
            state_combo.setEditText("")

        def _set_direction_checks(values: list[str | None]):
            direction_guard["block"] = True
            for item in direction_items:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            for value in values:
                item = direction_item_map.get(value)
                if item:
                    item.setCheckState(QtCore.Qt.CheckState.Checked)
            direction_guard["block"] = False

        def _selected_directions() -> list[str]:
            selected: list[str] = []
            for item in direction_items:
                if item.checkState() == QtCore.Qt.CheckState.Checked:
                    value = item.data(QtCore.Qt.ItemDataRole.UserRole)
                    if value:
                        selected.append(value)
            return selected

        if existing_move:
            type_combo.setCurrentIndex(0)
            direction_tokens = self._split_direction_tokens(existing_move.direction)
            _set_direction_checks(direction_tokens or ["left"])
            speed_index = speed_combo.findData((existing_move.default_speed or "med").lower())
            if speed_index >= 0:
                speed_combo.setCurrentIndex(speed_index)
        elif default_type == "movement":
            type_combo.setCurrentIndex(0)
            _set_direction_checks(["left"])
        else:
            type_combo.setCurrentIndex(1)
            _set_direction_checks([None])

        def _toggle_fields():
            is_movement = type_combo.currentData() == "movement"
            direction_list.setEnabled(is_movement)
            speed_combo.setEnabled(is_movement)
            if not is_movement:
                _set_direction_checks([None])
            else:
                if not _selected_directions():
                    _set_direction_checks(["left"])

        def _on_direction_item_changed(item: QtWidgets.QListWidgetItem):
            if direction_guard["block"]:
                return
            value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                direction_guard["block"] = True
                if value in (None, "any"):
                    for other in direction_items:
                        if other is not item:
                            other.setCheckState(QtCore.Qt.CheckState.Unchecked)
                else:
                    any_item = direction_item_map.get("any")
                    none_item = direction_item_map.get(None)
                    if any_item:
                        any_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                    if none_item:
                        none_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                direction_guard["block"] = False
            else:
                if value is None and type_combo.currentData() == "transition":
                    # keep None selected for transition
                    direction_guard["block"] = True
                    item.setCheckState(QtCore.Qt.CheckState.Checked)
                    direction_guard["block"] = False

        _toggle_fields()
        type_combo.currentIndexChanged.connect(_toggle_fields)
        direction_list.itemChanged.connect(_on_direction_item_changed)

        def on_accept():
            key_value = key_edit.text().strip()
            if not key_value:
                QtWidgets.QMessageBox.warning(dialog, "Action", "Key cannot be empty.")
                return
            normalized_key = key_value.lower()
            if not action_key and normalized_key in w._move_state_defs:
                QtWidgets.QMessageBox.warning(dialog, "Action", "Action key already exists.")
                return

            state_value = state_combo.currentText().strip() or key_value
            if state_value not in w._state_defs:
                w._state_defs[state_value] = StateSettings(label=state_value.capitalize())
                self.ensure_local_gif_for_state(state_value)
                self.persist_state_definitions()
            action_type = type_combo.currentData()

            if action_type == "movement":
                selected_dirs = _selected_directions()
                if not selected_dirs:
                    selected_dirs = ["left"]
                direction_value = self._normalize_direction_value("|".join(selected_dirs))
                speed_value = speed_combo.currentData() or "med"
                self.register_move_state(
                    key_value,
                    state_key=state_value,
                    direction=direction_value,
                    default_distance=None,
                    default_speed=speed_value,
                )
                self.write_move_state_list()
                if action_path and Path(action_path).is_file():
                    target_state = w._state_defs.get(state_value)
                    if target_state:
                        target_state.gif_path = action_path
                        self._update_state_variants(state_value)
            else:
                removed = self.unregister_move_state(key_value)
                if removed:
                    self.write_move_state_list()
                if action_path and Path(action_path).is_file():
                    target_state = w._state_defs.get(state_value)
                    if target_state:
                        target_state.gif_path = action_path
                        self._update_state_variants(state_value)

            self.write_state_list()
            if refresh:
                refresh(key_value)
            dialog.accept()

        button_box.accepted.connect(on_accept)
        button_box.rejected.connect(dialog.reject)
        dialog.exec()

    def apply_move_gif_update(self, action_key: str):
        normalized = (action_key or "").strip().lower()
        if not normalized:
            return
        w = self._window
        move_settings = w._move_state_defs.get(normalized)
        if move_settings is None:
            return
        target_path = self.move_storage_path_for_key(normalized)
        if not target_path.is_file():
            return
        try:
            resolved = str(target_path.resolve())
        except OSError:
            resolved = str(target_path)
        target_state = w._state_defs.get(move_settings.state_key)
        if target_state and target_state.gif_path:
            try:
                candidate = Path(target_state.gif_path).resolve()
            except OSError:
                candidate = Path(target_state.gif_path)
            if candidate.is_file():
                return
        target_state_path = self.state_storage_path_for_key(move_settings.state_key)
        if target_state_path.is_file():
            return
        try:
            shutil.copy2(resolved, target_state_path)
        except OSError:
            return
        self._update_state_variants(move_settings.state_key)

    def ensure_walking_state_available(self) -> tuple[bool, bool]:
        w = self._window
        walking_key = "walking"
        step_default = max(12, int(w._movement_step_px))
        move_state_updated = self.register_move_state(
            walking_key,
            state_key=walking_key,
            direction="any",
            default_distance=float(step_default),
            default_speed="med",
        )
        walking_path = w._move_storage_dir / f"{walking_key}.gif"
        state_changed = False
        if not walking_path.is_file():
            if move_state_updated:
                self.write_move_state_list()
            walking_settings = w._state_defs.get(walking_key)
            if walking_settings:
                walking_settings.gif_variants = []
            return False, False
        path_str = str(walking_path.resolve())
        added = False
        settings = w._state_defs.get(walking_key)
        if settings is None:
            settings = StateSettings(label="Walking", gif_path=path_str)
            w._state_defs[walking_key] = settings
            if not hasattr(w, "_protected_state_keys"):
                w._protected_state_keys = set()
            w._protected_state_keys.add(walking_key)
            added = True
            state_changed = True
        else:
            if settings.gif_path != path_str:
                settings.gif_path = path_str
                state_changed = True
        if state_changed or move_state_updated:
            self.write_move_state_list()
        self._update_state_variants(walking_key)
        return True, added
    def ensure_local_gif_for_state(self, key: str):
        w = self._window
        settings = w._state_defs.get(key)
        if settings is None:
            return
        if key == "walking":
            walking_source = w._move_storage_dir / "walking.gif"
            if walking_source.is_file():
                settings.gif_path = str(walking_source.resolve())
            elif w._default_idle_gif.is_file():
                settings.gif_path = str(w._default_idle_gif.resolve())
            else:
                settings.gif_path = None
            self._update_state_variants(key)
            return
        current_path = settings.gif_path
        assigned = False
        if current_path:
            src = Path(current_path)
            if src.is_file():
                dest = self._state_storage_path_for_key(key)
                try:
                    if src.resolve() == dest.resolve():
                        settings.gif_path = str(dest.resolve())
                        assigned = True
                except OSError:
                    pass
        if not assigned:
            dest = self._state_storage_path_for_key(key)
            src = Path(settings.gif_path or "")
            if src.is_file():
                try:
                    shutil.copy2(src, dest)
                    settings.gif_path = str(dest)
                except OSError:
                    settings.gif_path = None
            elif w._default_idle_gif.is_file():
                settings.gif_path = str(w._default_idle_gif.resolve())
            else:
                settings.gif_path = None
        self._update_state_variants(key)
    def _update_state_variants(self, key: str):
        w = self._window
        settings = w._state_defs.get(key)
        if settings is None:
            return
        variants = []
        primary = settings.gif_path
        if primary:
            variants.append(primary)
        variants_dir = self._state_variants_dir_for_key(key)
        if variants_dir.is_dir():
            for path in sorted(variants_dir.glob("*.gif")):
                try:
                    resolved = str(path.resolve())
                except OSError:
                    resolved = str(path)
                variants.append(resolved)
        settings.gif_variants = variants

    def _select_state_gif_variant(self, key: str):
        w = self._window
        if w._state_settings is None:
            w._active_gif_path = None
            return
        settings = w._state_settings
        candidates: list[str] = []
        for path in settings.gif_variants:
            try:
                candidate = Path(path)
            except TypeError:
                continue
            if candidate.is_file():
                try:
                    resolved = str(candidate.resolve())
                except OSError:
                    resolved = str(candidate)
                if resolved not in candidates:
                    candidates.append(resolved)
        base_path = settings.gif_path
        base_resolved: str | None = None
        if base_path:
            try:
                base_candidate = Path(base_path)
            except TypeError:
                base_candidate = None
            if base_candidate and base_candidate.is_file():
                try:
                    base_resolved = str(base_candidate.resolve())
                except OSError:
                    base_resolved = str(base_candidate)
                if base_resolved not in candidates:
                    candidates.insert(0, base_resolved)
        if candidates:
            chosen = random.choice(candidates)
        elif base_resolved:
            chosen = base_resolved
        elif w._default_idle_gif.is_file():
            try:
                chosen = str(w._default_idle_gif.resolve())
            except OSError:
                chosen = str(w._default_idle_gif)
        else:
            chosen = None
        if chosen and not Path(chosen).is_file():
            chosen = None
        if chosen and base_resolved and chosen == base_resolved:
            w._active_gif_path = None
        else:
            w._active_gif_path = chosen
