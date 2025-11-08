from __future__ import annotations

import copy
import json
import random
import shutil
from dataclasses import dataclass, field, asdict, fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class StateSettings:
    label: str
    bob_amplitude: float = 6.0
    scale_amplitude: float = 0.04
    gradient_top: str = "#FFFFFFFF"
    gradient_mid: str = "#FF9BE3FF"
    gradient_bottom: str = "#FF6CC1F0"
    cheeks_alpha: float = 204
    blush_color: str = "#FFC0C0"
    eye_color: str = "#222222"
    bubble_visible: bool = True
    bubble_alpha: float = 170
    name_tag: str = "doro"
    gif_path: str | None = None
    gif_variants: list[str] = field(default_factory=list)


class StateManagerMixin:
    """Encapsulates state storage, persistence, and management helpers."""

    def _init_state_manager(self, base_dir: Path):
        self._state_defs: dict[str, StateSettings] = {}
        self._protected_state_keys: set[str] = set()
        self._state_settings: StateSettings | None = None
        self._active_gif_path: str | None = None
        self._current_state_key: str = ""
        self._state_list_text: str = ""
        self._action_state_list_text: str = ""
        self._state_storage_dir = base_dir / "res" / "state"
        self._state_storage_dir.mkdir(parents=True, exist_ok=True)
        self._action_storage_dir = base_dir / "res" / "action"
        self._action_storage_dir.mkdir(parents=True, exist_ok=True)
        self._default_idle_gif = self._state_storage_dir / "idle.gif"
        self._state_list_path = self._state_storage_dir / "state_list.txt"
        self._action_state_list_path = self._state_storage_dir / "action_state_list.txt"
        self._state_config_path = self._state_storage_dir / "states.json"
        if not hasattr(self, "_action_state_defs"):
            self._action_state_defs = {}
        if not hasattr(self, "_action_only_state_keys"):
            self._action_only_state_keys = set()
        legacy_move_dir = base_dir / "res" / "move"
        if legacy_move_dir.is_dir() and legacy_move_dir != self._action_storage_dir:
            for src in legacy_move_dir.glob("*.gif"):
                dest = self._action_storage_dir / src.name
                if dest.exists():
                    continue
                try:
                    shutil.move(str(src), dest)
                except OSError:
                    try:
                        shutil.copy2(src, dest)
                    except OSError:
                        pass
        legacy_list = self._state_storage_dir / "move_state_list.txt"
        if legacy_list.is_file() and not self._action_state_list_path.exists():
            try:
                legacy_list.rename(self._action_state_list_path)
            except OSError:
                try:
                    shutil.copy2(legacy_list, self._action_state_list_path)
                except OSError:
                    pass

    # --- State lifecycle -------------------------------------------------
    def _init_states(self):
        default_defs = self._default_state_definitions()
        self._protected_state_keys = set(default_defs.keys())
        self._state_defs = self._build_state_definitions(default_defs)
        self._ensure_walking_state_available()

        preferred_key = self._config.value("current_state", "idle")
        if preferred_key not in self._state_defs:
            preferred_key = "idle" if "idle" in self._state_defs else next(iter(self._state_defs), "")
        if preferred_key:
            self._set_state(preferred_key)
        elif self._state_defs:
            self._set_state(next(iter(self._state_defs)))

        self._write_state_list()
        self._write_action_state_list()

    def _default_state_definitions(self) -> dict[str, StateSettings]:
        defs = {
            "idle": StateSettings(label="Idle"),
        }
        idle_path = self._walking_gif_path()
        if idle_path:
            for state in defs.values():
                state.gif_path = idle_path
        return defs

    def _read_state_config(self) -> dict[str, StateSettings]:
        if not self._state_config_path.is_file():
            return {}
        try:
            payload = json.loads(self._state_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        results: dict[str, StateSettings] = {}
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            normalized = (key or "").strip().lower()
            if not normalized or normalized in self._action_only_state_keys:
                continue
            results[key] = self._state_settings_from_dict(key, value)
        return results

    def _build_state_definitions(self, defaults: dict[str, StateSettings]) -> dict[str, StateSettings]:
        definitions: dict[str, StateSettings] = {
            key: copy.deepcopy(settings) for key, settings in defaults.items()
        }
        for key, settings in self._read_state_config().items():
            definitions[key] = settings

        hydrated: dict[str, StateSettings] = {}
        for key, settings in definitions.items():
            stored_path = self._config.value(f"state/{key}/gif_path", "", str) or None
            if stored_path:
                settings.gif_path = stored_path
            hydrated[key] = self._resolve_state_media(key, settings)
        return hydrated

    def _persist_current_state(self):
        if not self._current_state_key:
            return
        self._config.setValue("current_state", self._current_state_key)
        if self._state_settings:
            path = self._state_settings.gif_path or ""
            self._config.setValue(f"state/{self._current_state_key}/gif_path", path)

    # --- State queries ---------------------------------------------------
    def _is_action_only_state(self, key: str) -> bool:
        return key.strip().lower() in self._action_only_state_keys

    def _visible_state_keys(self) -> list[str]:
        return [key for key in self._state_defs if not self._is_action_only_state(key)]

    # --- State switching -------------------------------------------------
    def _set_state(self, key: str):
        if key not in self._state_defs:
            return
        if self._current_state_key and self._state_settings:
            self._state_defs[self._current_state_key] = copy.deepcopy(self._state_settings)
        self._current_state_key = key
        self._active_gif_path = None
        self._state_settings = copy.deepcopy(self._state_defs[key])
        self._select_state_gif_variant(key)
        self._apply_state_settings()
        self.update()
        self._persist_current_state()

    def _reset_state_overrides(self):
        if not self._current_state_key:
            return
        self._active_gif_path = None
        self._state_settings = copy.deepcopy(self._state_defs[self._current_state_key])
        self._apply_state_settings()
        self.update()
        self._persist_current_state()

    # --- State assets ----------------------------------------------------
    def _load_state_gif(self):
        if not self._state_defs:
            return
        self._show_state_gif_manager()

    def _set_state_gif_from_path(self, key: str, source_path: str) -> bool:
        if key not in self._state_defs:
            return False
        if not Path(source_path).is_file():
            QtWidgets.QMessageBox.warning(self, "Load GIF", "The selected file does not exist.")
            return False

        dest_path = self._state_storage_path_for_key(key)
        try:
            shutil.copy2(source_path, dest_path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Load GIF",
                f"Failed to copy GIF to internal storage:\n{exc}",
            )
            return False

        if key == self._current_state_key and self._state_settings is not None:
            self._state_settings.gif_path = str(dest_path)
            self._active_gif_path = None
            self._apply_state_settings()
            if self._gif_movie is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Load GIF",
                    "Failed to load the selected GIF.",
                )
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except OSError:
                        pass
                if self._default_idle_gif.is_file():
                    self._state_settings.gif_path = str(self._default_idle_gif)
                else:
                    self._state_settings.gif_path = None
                try:
                    self._save_state_settings()
                    self._apply_state_settings()
                finally:
                    self.update()
                return False
            self._save_state_settings()
            self.update()
        else:
            movie = QtGui.QMovie(str(dest_path))
            if not movie.isValid():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Load GIF",
                    "Failed to load the selected GIF for this state.",
                )
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except OSError:
                        pass
                fallback = str(self._default_idle_gif) if self._default_idle_gif.is_file() else None
                target_settings = self._state_defs[key]
                target_settings.gif_path = fallback
                self._refresh_state_definition(key)
                return False
            self._state_defs[key].gif_path = str(dest_path)

        refreshed = self._refresh_state_definition(key)
        if key == self._current_state_key and self._state_settings and refreshed:
            self._state_settings.gif_variants = list(refreshed.gif_variants)
        self._write_state_list()
        return True

    def _state_storage_token(self, key: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        if not safe:
            safe = "state"
        return safe

    def _state_storage_path_for_key(self, key: str) -> Path:
        return self._state_storage_dir / f"{self._state_storage_token(key)}.gif"

    def _state_variants_dir_for_key(self, key: str) -> Path:
        return self._state_storage_dir / f"{self._state_storage_token(key)}_variants"

    def _action_storage_path_for_key(self, key: str) -> Path:
        safe = self._state_storage_token(key)
        return self._action_storage_dir / f"{safe}.gif"

    def _apply_action_gif_update(self, action_key: str):
        normalized = (action_key or "").strip().lower()
        if not normalized:
            return
        action_settings = self._action_state_defs.get(normalized)
        if action_settings is None:
            return
        target_path = self._action_storage_path_for_key(normalized)
        if not target_path.is_file():
            return
        try:
            resolved = str(target_path.resolve())
        except OSError:
            resolved = str(target_path)
        state_key = action_settings.state_key
        state_settings = self._state_defs.get(state_key)
        if state_settings:
            if state_settings.gif_path != resolved:
                state_settings.gif_path = resolved
            refreshed = self._refresh_state_definition(state_key)
            if self._current_state_key == state_key and self._state_settings is not None:
                self._state_settings.gif_path = resolved
                if refreshed:
                    self._state_settings.gif_variants = list(refreshed.gif_variants)
                self._active_gif_path = None
                self._apply_state_settings()
                self.update()
            self._config.setValue(f"state/{state_key}/gif_path", resolved)
        self._write_state_list()
        self._write_action_state_list()
        if state_key == self._current_state_key:
            self._persist_current_state()
        else:
            self._persist_state_definitions()

    def _refresh_state_definition(self, key: str) -> StateSettings | None:
        settings = self._state_defs.get(key)
        if not settings:
            return None
        updated = self._resolve_state_media(key, settings)
        self._state_defs[key] = updated
        return updated

    # Backward-compatible no-op wrapper for legacy callers.
    def _update_state_variants(self, key: str):
        self._refresh_state_definition(key)

    def _select_state_gif_variant(self, key: str):
        if self._state_settings is None:
            self._active_gif_path = None
            return
        settings = self._state_settings
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
        chosen: str | None
        if candidates:
            # Temporarily disable random choice to debug variant issue
            chosen = base_resolved or (candidates[0] if candidates else None)
        elif base_resolved:
            chosen = base_resolved
        elif self._default_idle_gif.is_file():
            try:
                chosen = str(self._default_idle_gif.resolve())
            except OSError:
                chosen = str(self._default_idle_gif)
        else:
            chosen = None
        if chosen and not Path(chosen).is_file():
            chosen = None
        if chosen and base_resolved and chosen == base_resolved:
            self._active_gif_path = None
        else:
            self._active_gif_path = chosen

    def _resolve_state_media(self, key: str, source: StateSettings) -> StateSettings:
        settings = copy.deepcopy(source)
        if key == "walking":
            settings.gif_path = self._walking_gif_path()
            settings.gif_variants = self._discover_state_variants(key, settings.gif_path)
            return settings

        primary = settings.gif_path
        resolved_path: str | None = None
        if primary:
            src = Path(primary)
            if src.is_file():
                dest = self._state_storage_path_for_key(key)
                resolved_path = self._copy_state_gif(src, dest)
        if not resolved_path:
            resolved_path = self._default_idle_path()
        settings.gif_path = resolved_path
        settings.gif_variants = self._discover_state_variants(key, resolved_path)
        return settings

    def _default_idle_path(self) -> str | None:
        if self._default_idle_gif.is_file():
            try:
                return str(self._default_idle_gif.resolve())
            except OSError:
                return str(self._default_idle_gif)
        return None

    def _walking_gif_path(self) -> str | None:
        walking_source = self._action_storage_dir / "walking.gif"
        if walking_source.is_file():
            try:
                return str(walking_source.resolve())
            except OSError:
                return str(walking_source)
        return self._default_idle_path()

    def _copy_state_gif(self, src: Path, dest: Path) -> str | None:
        try:
            src_resolved = src.resolve()
            dest_resolved = dest.resolve()
            if src_resolved == dest_resolved and dest.is_file():
                return str(dest_resolved)
        except OSError:
            pass
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except shutil.SameFileError:
            try:
                return str(dest.resolve())
            except OSError:
                return str(dest)
        except OSError:
            return None
        try:
            return str(dest.resolve())
        except OSError:
            return str(dest)

    def _discover_state_variants(self, key: str, primary_path: str | None) -> list[str]:
        variants: list[str] = []
        if primary_path:
            try:
                normalized = str(Path(primary_path).resolve())
            except OSError:
                normalized = primary_path
            if Path(normalized).is_file():
                variants.append(normalized)
        variants_dir = self._state_variants_dir_for_key(key)
        if variants_dir.is_dir():
            for path in sorted(variants_dir.glob("*.gif")):
                try:
                    resolved = str(path.resolve())
                except OSError:
                    resolved = str(path)
                if resolved not in variants and path.is_file():
                    variants.append(resolved)
        return variants

    # --- Persistence -----------------------------------------------------
    def _save_state_settings(self):
        if not self._current_state_key or self._state_settings is None:
            return
        self._state_defs[self._current_state_key] = copy.deepcopy(self._state_settings)
        self._persist_current_state()
        self._persist_state_definitions()

    def _state_settings_to_dict(self, settings: StateSettings) -> dict:
        data = asdict(settings)
        data.pop("gif_path", None)
        data.pop("gif_variants", None)
        return data

    def _state_settings_from_dict(self, key: str, data: dict) -> StateSettings:
        allowed = {field.name for field in dataclass_fields(StateSettings)}
        clean = {
            k: v
            for k, v in data.items()
            if k in allowed and k not in {"gif_path", "gif_variants"}
        }
        if "label" not in clean or not str(clean["label"]).strip():
            clean["label"] = key.capitalize()
        return StateSettings(**clean)

    def _persist_state_definitions(self):
        custom_states = {
            key: self._state_settings_to_dict(settings)
            for key, settings in self._state_defs.items()
            if key not in self._protected_state_keys
        }
        try:
            if custom_states:
                self._state_config_path.parent.mkdir(parents=True, exist_ok=True)
                self._state_config_path.write_text(
                    json.dumps(custom_states, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                if self._state_config_path.exists():
                    self._state_config_path.unlink()
        except OSError:
            pass

    def _write_state_list(self):
        lines = []
        for key in sorted(self._state_defs.keys()):
            state = self._state_defs[key]
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
            lines.append(f"- ({key}) {label} | GIF: {gif_hint}")
        output = "\n".join(lines) + "\n"
        new_text = output.strip()
        if getattr(self, "_state_list_text", None) == new_text:
            return
        self._state_list_text = new_text
        try:
            self._state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    def _write_action_state_list(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{timestamp}] 可使用的動作狀態為:"]
        action_defs = getattr(self, "_action_state_defs", {})
        if not action_defs:
            lines.append("- (none) 無動作狀態")
        else:
            for key in sorted(action_defs.keys()):
                action_settings = action_defs[key]
                direction = (action_settings.direction or "any").strip() or "any"
                direction = direction.lower()
                state_key = action_settings.state_key
                state_settings = self._state_defs.get(state_key)
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
        new_text = output.strip()
        if getattr(self, "_action_state_list_text", None) == new_text:
            return
        self._action_state_list_text = new_text
        try:
            self._action_state_list_path.write_text(output, encoding="utf-8")
        except OSError:
            pass
        print(output)

    # --- Dialog helpers --------------------------------------------------
    def _remove_state_gif_variant(self, key: str, variant_path: str, *, parent: QtWidgets.QWidget | None = None) -> bool:
        if key not in self._state_defs:
            return False
        path = Path(variant_path)
        if not path.is_file():
            return False
        try:
            path.unlink()
        except OSError:
            QtWidgets.QMessageBox.warning(
                parent or self,
                "Remove GIF variant",
                "Failed to delete the variant file.",
            )
            return False
        refreshed = self._refresh_state_definition(key)
        if key == self._current_state_key and self._state_settings and refreshed:
            self._state_settings.gif_variants = list(refreshed.gif_variants)
            self._select_state_gif_variant(key)
            self._apply_state_settings()
            self.update()
        self._write_state_list()
        return True

    def _show_state_gif_collection(self, state_key: str, *, parent: QtWidgets.QWidget | None = None):
        if state_key not in self._state_defs:
            return
        state = self._refresh_state_definition(state_key)
        if state is None:
            return

        dialog_parent = parent or self
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

        add_button = QtWidgets.QPushButton("Add variant…")
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
            movie.setScaledSize(QtCore.QSize(160, 160))
            preview_label.setMovie(movie)
            movie.start()
            preview_movie[0] = movie

        def repopulate(select_path: str | None = None):
            list_widget.clear()
            entries: list[tuple[str, str]] = []
            settings = self._state_defs.get(state_key)
            if not settings:
                return
            main_path = settings.gif_path
            if main_path:
                entries.append(("primary", main_path))
            for variant in settings.gif_variants or []:
                if variant and variant != main_path:
                    entries.append(("variant", variant))
            if not entries:
                list_widget.addItem("(no GIFs)")
                list_widget.setEnabled(False)
                set_main_button.setEnabled(False)
                remove_button.setEnabled(False)
                preview_label.setText("No GIF selected")
                return

            list_widget.setEnabled(True)
            for kind, path in entries:
                suffix = " (main)" if kind == "primary" else ""
                item = QtWidgets.QListWidgetItem(f"{path}{suffix}")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, (kind, path))
                list_widget.addItem(item)
                if select_path and path == select_path:
                    item.setSelected(True)
            if not list_widget.selectedItems():
                list_widget.setCurrentRow(0)
            current = list_widget.currentItem()
            if current:
                kind, path = current.data(QtCore.Qt.ItemDataRole.UserRole)
                set_main_button.setEnabled(kind == "variant")
                remove_button.setEnabled(kind == "variant")
                show_preview(path)

        def current_entry():
            item = list_widget.currentItem()
            if not item:
                return None
            return item.data(QtCore.Qt.ItemDataRole.UserRole)

        def add_variant():
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog,
                "Add GIF variant",
                str(self._state_storage_dir),
                "GIF files (*.gif)",
            )
            if not file_path:
                return
            src = Path(file_path)
            if not src.is_file():
                QtWidgets.QMessageBox.warning(dialog, "Add GIF variant", "The selected file does not exist.")
                return
            variants_dir = self._state_variants_dir_for_key(state_key)
            variants_dir.mkdir(parents=True, exist_ok=True)
            dest = variants_dir / src.name
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Add GIF variant",
                    f"Failed to copy GIF:\n{exc}",
                )
                return
            self._refresh_state_definition(state_key)
            repopulate(select_path=str(dest))

        def set_selected_as_main():
            entry = current_entry()
            if not entry:
                return
            kind, path = entry
            if kind != "variant":
                return
            settings = self._state_defs.get(state_key)
            if not settings:
                return
            settings.gif_path = path
            self._refresh_state_definition(state_key)
            self._save_state_settings()
            new_main = self._state_defs[state_key].gif_path
            repopulate(select_path=new_main)

        def remove_variant():
            entry = current_entry()
            if not entry:
                return
            kind, path = entry
            if kind != "variant":
                return
            if QtWidgets.QMessageBox.question(
                dialog,
                "Remove GIF variant",
                "Remove this GIF variant?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            ) != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            if self._remove_state_gif_variant(state_key, path, parent=dialog):
                repopulate()

        add_button.clicked.connect(add_variant)
        set_main_button.clicked.connect(set_selected_as_main)
        remove_button.clicked.connect(remove_variant)
        close_button.clicked.connect(dialog.close)

        repopulate()
        dialog.finished.connect(lambda _code: stop_preview())
        dialog.exec()

    def _show_state_gif_manager(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("State GIFs")
        dialog.setObjectName("doroStateDialog")
        dialog.setMinimumWidth(840)
        dialog.setStyleSheet("#doroStateDialog { background-color: #060b15; border-radius: 22px; }")
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        header_frame = QtWidgets.QFrame(dialog)
        header_frame.setObjectName("gifHeaderFrame")
        header_layout = QtWidgets.QVBoxLayout(header_frame)
        header_layout.setContentsMargins(22, 22, 22, 22)
        header_layout.setSpacing(10)
        title = QtWidgets.QLabel("Manage animations for each state")
        title.setStyleSheet(
            "font-weight: 600; font-size: 18px; letter-spacing: 0.3px; color: #f8fbff;"
        )
        subtitle = QtWidgets.QLabel(
            "Preview existing GIFs, assign new ones, or add brand-new states. The highlighted row shows the current state."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #9fb4d0; font-size: 13px; line-height: 1.4;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_frame)

        header_frame.setStyleSheet(
            "#gifHeaderFrame {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #131f34, stop:1 #1f2f52);"
            "border-radius: 18px;"
            "border: 1px solid rgba(167, 139, 250, 0.25);"
            "}"
        )
        self._apply_card_shadow(header_frame, blur_radius=36, y_offset=14, opacity=180)

        table = QtWidgets.QTableWidget(dialog)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["State", "Preview", "Path", "Edit GIFs", "Assign GIF", "Delete"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        table.setStyleSheet(
            "QTableWidget {"
            "background-color: transparent;"
            "alternate-background-color: rgba(15,23,42,0.25);"
            "color: #e2e8f0;"
            "}"
            "QTableWidget::item:selected {"
            "background-color: rgba(103, 232, 249, 0.12);"
            "border-radius: 10px;"
            "}"
            "QTableCornerButton::section { background: transparent; }"
        )
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setStyleSheet(
            "QHeaderView::section {"
            "background-color: rgba(255, 255, 255, 0.05);"
            "color: #cbd5f5;"
            "border: none;"
            "border-bottom: 1px solid rgba(148, 163, 184, 0.2);"
            "font-weight: 600;"
            "padding: 8px;"
            "}"
        )
        layout.addWidget(table, stretch=1)

        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table._preview_movies: list[QtGui.QMovie] = []

        def clear_previews():
            for movie in table._preview_movies:
                try:
                    if movie:
                        movie.stop()
                except RuntimeError:
                    continue
            table._preview_movies = []

        def choose_for_key(state_key: str):
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog,
                f"Select GIF for '{state_key}'",
                str(self._state_storage_dir),
                "GIF files (*.gif)",
            )
            if not file_path:
                return
            if self._set_state_gif_from_path(state_key, file_path):
                repopulate(state_key=state_key)

        def repopulate(*, state_key: str | None = None):
            clear_previews()
            table.setRowCount(0)
            for row_index, key in enumerate(self._visible_state_keys()):
                state = self._state_defs[key]
                table.insertRow(row_index)

                label_item = QtWidgets.QTableWidgetItem(state.label or key)
                label_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row_index, 0, label_item)

                preview_label = QtWidgets.QLabel()
                preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                preview_label.setStyleSheet(
                    "background: rgba(15, 23, 42, 0.6);"
                    "border-radius: 18px;"
                    "border: 1px solid rgba(148, 163, 184, 0.35);"
                    "color: #94a3b8;"
                )
                preview_shadow = QtWidgets.QGraphicsDropShadowEffect(preview_label)
                preview_shadow.setBlurRadius(30)
                preview_shadow.setColor(QtGui.QColor(4, 7, 20, 140))
                preview_shadow.setOffset(0, 8)
                preview_label.setGraphicsEffect(preview_shadow)
                table.setRowHeight(row_index, 138)
                table.setCellWidget(row_index, 1, preview_label)

                preview_path = None
                raw_path = state.gif_path
                if raw_path and Path(raw_path).is_file():
                    preview_path = raw_path
                elif self._default_idle_gif.is_file():
                    preview_path = str(self._default_idle_gif)

                if preview_path:
                    movie = QtGui.QMovie(preview_path)
                    if movie.isValid():
                        movie.setScaledSize(QtCore.QSize(108, 108))
                        preview_label.setMovie(movie)
                        movie.start()
                        table._preview_movies.append(movie)
                    else:
                        preview_label.setText("Invalid GIF")
                        preview_label.setStyleSheet(
                            "color: #fecdd3; font-weight: 600; background-color: rgba(190, 52, 85, 0.14);"
                            "border-radius: 18px; border: 1px dashed rgba(255, 138, 173, 0.6);"
                        )
                else:
                    preview_label.setText("No preview")
                    preview_label.setStyleSheet(
                        "color: #8da2c3; font-weight: 600; background-color: rgba(15, 23, 42, 0.25);"
                        "border-radius: 18px; border: 1px dashed rgba(148, 163, 184, 0.45);"
                    )

                path_item = QtWidgets.QTableWidgetItem(state.gif_path or "(no GIF)")
                path_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
                table.setItem(row_index, 2, path_item)

                edit_button = QtWidgets.QPushButton("Edit…")
                edit_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
                edit_button.setStyleSheet(
                    "QPushButton {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a5b4fc, stop:1 #38bdf8);"
                    "color: #05070f;"
                    "font-weight: 600;"
                    "border-radius: 12px;"
                    "padding: 8px 18px;"
                    "}"
                    "QPushButton:hover {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #c7d2fe, stop:1 #7dd3fc);"
                    "}"
                )
                edit_button.clicked.connect(lambda _checked=False, k=key: self._show_state_gif_collection(k, parent=dialog))
                table.setCellWidget(row_index, 3, edit_button)

                assign_button = QtWidgets.QPushButton("Browse…")
                assign_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
                assign_button.setStyleSheet(
                    "QPushButton {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22d3ee, stop:1 #6366f1);"
                    "color: #05070f;"
                    "font-weight: 600;"
                    "border-radius: 12px;"
                    "padding: 8px 20px;"
                    "}"
                    "QPushButton:hover {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #67e8f9, stop:1 #818cf8);"
                    "}"
                )
                assign_button.clicked.connect(lambda _checked=False, k=key: choose_for_key(k))
                table.setCellWidget(row_index, 4, assign_button)

                remove_button = QtWidgets.QPushButton("Remove")
                remove_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
                remove_button.setStyleSheet(
                    "QPushButton {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f87171, stop:1 #fb7185);"
                    "color: #05070f;"
                    "font-weight: 600;"
                    "border-radius: 12px;"
                    "padding: 8px 18px;"
                    "}"
                    "QPushButton:hover {"
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fca5a5, stop:1 #fda4af);"
                    "}"
                    "QPushButton:disabled {"
                    "background: rgba(148,163,184,0.25);"
                    "color: rgba(248,250,252,0.55);"
                    "}"
                )
                can_remove = key not in self._protected_state_keys
                remove_button.setEnabled(can_remove)
                remove_button.clicked.connect(lambda _checked=False, k=key: self._remove_state_by_key(k, parent=dialog))
                table.setCellWidget(row_index, 5, remove_button)

                if state_key and key == state_key:
                    label_item.setSelected(True)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(12)
        add_state_button = QtWidgets.QPushButton("Add state…")
        add_state_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        add_state_button.setStyleSheet(
            "QPushButton {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #22d3ee);"
            "color: #05070f;"
            "font-weight: 600;"
            "border-radius: 12px;"
            "padding: 8px 24px;"
            "}"
            "QPushButton:hover {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6ee7b7, stop:1 #67e8f9);"
            "}"
        )
        add_state_button.clicked.connect(self._add_state)
        button_row.addWidget(add_state_button)

        close_button = QtWidgets.QPushButton("Close")
        close_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        close_button.setStyleSheet(
            "QPushButton {"
            "background: rgba(148,163,184,0.25);"
            "color: #e2e8f0;"
            "border-radius: 12px;"
            "padding: 8px 24px;"
            "}"
            "QPushButton:hover {"
            "background: rgba(148,163,184,0.4);"
            "}"
        )
        close_button.clicked.connect(dialog.close)
        button_row.addWidget(close_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        repopulate(state_key=self._current_state_key)
        dialog.finished.connect(lambda _code: clear_previews())
        dialog.exec()

    def _add_state(self, checked: bool = False) -> str | None:
        key, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add new state",
            "Unique state key:",
        )
        if not ok:
            return None
        key = key.strip()
        if not key:
            return None
        normalized_key = key.lower()
        if normalized_key in self._action_only_state_keys:
            QtWidgets.QMessageBox.warning(
                self,
                "Add state",
                "This key is reserved for action animations.",
            )
            return None
        if key in self._state_defs:
            QtWidgets.QMessageBox.warning(
                self,
                "Add state",
                "A state with this key already exists.",
            )
            return None

        default_label = key.capitalize()
        label, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add new state",
            "Display name:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            default_label,
        )
        if not ok:
            return None
        label = label.strip() or default_label

        base_settings = (
            copy.deepcopy(self._state_settings)
            if self._state_settings is not None
            else StateSettings(label=label)
        )
        base_settings.label = label
        base_settings.name_tag = base_settings.name_tag or label
        self._state_defs[key] = base_settings
        self._refresh_state_definition(key)
        self._set_state(key)
        self._persist_state_definitions()
        return key

    def _remove_state_by_key(
        self,
        key: str,
        *,
        confirm: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> bool:
        if not key or key not in self._state_defs:
            return False
        if key in self._protected_state_keys:
            return False

        target_parent = parent or self
        state_label = self._state_defs[key].label or key
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

        settings = self._state_defs[key]
        stored_path = Path(settings.gif_path or "")
        if stored_path.is_file():
            try:
                stored_path.relative_to(self._state_storage_dir)
            except ValueError:
                pass
            else:
                if stored_path != self._default_idle_gif:
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
        self._config.remove(f"state/{key}/gif_path")

        del self._state_defs[key]
        if self._current_state_key == key:
            visible_keys = self._visible_state_keys()
            if visible_keys:
                next_key = "idle" if "idle" in visible_keys else visible_keys[0]
                self._set_state(next_key)
            else:
                self._current_state_key = ""
                self._state_settings = None
                self.update()
                self._config.setValue("current_state", "")
        else:
            self._persist_current_state()

        self._persist_state_definitions()
        self._write_state_list()
        return True

    def _remove_current_state(self):
        if not self._current_state_key:
            return
        self._remove_state_by_key(self._current_state_key)


__all__ = ["StateManagerMixin", "StateSettings"]
