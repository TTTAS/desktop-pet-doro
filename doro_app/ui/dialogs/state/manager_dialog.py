"""State Manager Dialog - manage all states with GIF previews (card grid)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import State, StateService
from ...components.gif_player import GifPlayer
from ...components.frameless_dialog import FramelessDialog


# ───────────────────────────────────────────────────────────
# State Card Widget
# ───────────────────────────────────────────────────────────

class _StateCard(QtWidgets.QFrame):
    """A card displaying a single state with GIF preview and actions."""

    edit_gif_clicked = QtCore.Signal(str)   # state_key
    edit_clicked = QtCore.Signal(str)       # state_key
    remove_clicked = QtCore.Signal(str)     # state_key

    CARD_WIDTH = 200
    PREVIEW_SIZE = 128

    def __init__(
        self,
        state: State,
        key: str,
        gif_paths: list[Path],
        gif_player: GifPlayer,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self._key = key
        self._gif_paths = gif_paths
        self._gif_player = gif_player
        self._preview_index = 0

        self.setObjectName("stateCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setStyleSheet(
            "#stateCard { background: #ffffff; border: 1px solid rgba(232,96,156,0.25);"
            " border-radius: 12px; }"
            "#stateCard:hover { border-color: #e8609c;"
            " background: #fff8fb; }"
        )
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._build(state)

    def _build(self, state: State):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # ── GIF preview area ──
        preview_row = QtWidgets.QHBoxLayout()
        preview_row.setSpacing(2)

        self._left_btn = self._arrow_button("left")
        self._left_btn.clicked.connect(lambda: self._navigate(-1))
        preview_row.addWidget(self._left_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        self._preview = QtWidgets.QLabel()
        self._preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
        self._preview.setStyleSheet(
            "background: #fff5fa; border-radius: 8px;"
        )
        preview_row.addWidget(self._preview, 1, QtCore.Qt.AlignmentFlag.AlignCenter)

        self._right_btn = self._arrow_button("right")
        self._right_btn.clicked.connect(lambda: self._navigate(1))
        preview_row.addWidget(self._right_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(preview_row)

        # Counter
        count = len(self._gif_paths)
        self._counter = QtWidgets.QLabel(
            f"1/{count}" if count > 0 else "No GIF"
        )
        self._counter.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._counter.setStyleSheet("font-size: 11px; color: #e8609c; font-weight: 600;")
        layout.addWidget(self._counter)

        # Hide arrows if <= 1 GIF
        if count <= 1:
            self._left_btn.setVisible(False)
            self._right_btn.setVisible(False)

        # Load first GIF
        if self._gif_paths:
            movie = self._gif_player.load(
                self._gif_paths[0], size=QtCore.QSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
            )
            if movie:
                self._preview.setMovie(movie)

        # ── Label ──
        label_text = state.label or self._key
        name = QtWidgets.QLabel(label_text)
        name.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 13px; font-weight: bold; color: #4a2040;")
        name.setWordWrap(True)
        layout.addWidget(name)

        key_label = QtWidgets.QLabel(self._key)
        key_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        key_label.setStyleSheet("font-size: 11px; color: #9c6b8a;")
        layout.addWidget(key_label)

        # ── Action buttons ──
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(4)

        manage_btn = QtWidgets.QPushButton("GIFs")
        manage_btn.setToolTip("Manage GIFs")
        manage_btn.setFixedHeight(26)
        manage_btn.setStyleSheet(self._small_btn_style())
        manage_btn.clicked.connect(lambda: self.edit_gif_clicked.emit(self._key))
        btn_row.addWidget(manage_btn)

        remove_btn = QtWidgets.QPushButton("Del")
        remove_btn.setToolTip("Remove state")
        remove_btn.setFixedHeight(26)
        remove_btn.setStyleSheet(self._small_btn_danger_style())
        remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self._key))
        btn_row.addWidget(remove_btn)

        layout.addLayout(btn_row)

    # ── Navigation ──

    def _navigate(self, direction: int):
        if not self._gif_paths:
            return
        count = len(self._gif_paths)
        self._preview_index = (self._preview_index + direction) % count
        movie = self._gif_player.load(
            self._gif_paths[self._preview_index],
            size=QtCore.QSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE),
        )
        if movie:
            self._preview.setMovie(movie)
        self._counter.setText(f"{self._preview_index + 1}/{count}")

    # ── Helpers ──

    def _arrow_button(self, direction: str) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton()
        btn.setFixedSize(22, 22)
        btn.setIcon(self._make_arrow_icon(direction))
        btn.setIconSize(QtCore.QSize(14, 14))
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; }"
            "QPushButton:hover { background: rgba(232,96,156,0.12); border-radius: 11px; }"
        )
        return btn

    @staticmethod
    def _make_arrow_icon(direction: str) -> QtGui.QIcon:
        px = QtGui.QPixmap(14, 14)
        px.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(px)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor("#e8609c"))
        if direction == "left":
            pts = [QtCore.QPointF(10, 2), QtCore.QPointF(4, 7), QtCore.QPointF(10, 12)]
        else:
            pts = [QtCore.QPointF(4, 2), QtCore.QPointF(10, 7), QtCore.QPointF(4, 12)]
        p.drawPolygon(pts)
        p.end()
        return QtGui.QIcon(px)

    @staticmethod
    def _small_btn_style() -> str:
        return (
            "QPushButton { background: rgba(232,96,156,0.12); color: #c0266e;"
            " border: none; border-radius: 6px; padding: 2px 8px;"
            " font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(232,96,156,0.25); }"
        )

    @staticmethod
    def _small_btn_danger_style() -> str:
        return (
            "QPushButton { background: rgba(200,40,40,0.10); color: #c62828;"
            " border: none; border-radius: 6px; padding: 2px 8px;"
            " font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(200,40,40,0.22); }"
        )


# ───────────────────────────────────────────────────────────
# State Manager Dialog
# ───────────────────────────────────────────────────────────

class StateManagerDialog(FramelessDialog):
    """Dialog for managing states — card grid layout."""

    def __init__(self, service: StateService, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("State Manager", parent)
        self.service = service
        self.setMinimumWidth(660)
        self.setMinimumHeight(480)
        self._gif_player = GifPlayer()
        self._cards: list[_StateCard] = []
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = self.content_layout

        # Scroll area
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._grid_container = QtWidgets.QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = QtWidgets.QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(14)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        # Bottom buttons
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()

        add_btn = QtWidgets.QPushButton("Add State")
        add_btn.clicked.connect(self._on_add)
        button_row.addWidget(add_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def _populate(self):
        # Clear old cards
        self._gif_player.clear()
        self._cards.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        visible_keys = sorted(self.service.visible_state_keys())
        cols = max(1, (self.width() - 80) // (_StateCard.CARD_WIDTH + 14))

        for i, key in enumerate(visible_keys):
            state = self.service.get_state(key)
            if not state:
                continue

            gif_paths = self._get_all_gif_paths(state, key)
            card = _StateCard(state, key, gif_paths, self._gif_player, self._grid_container)
            card.edit_gif_clicked.connect(self._on_edit_gif)
            card.remove_clicked.connect(self._on_remove)
            self._grid_layout.addWidget(card, i // cols, i % cols)
            self._cards.append(card)

    # ── GIF path helpers ──

    def _get_all_gif_paths(self, state: State, key: str) -> list[Path]:
        multi_gifs = self.service.list_gif_paths(key)
        if multi_gifs:
            return multi_gifs

        if state.gif_id:
            gif_path = self.service.get_gif_path_by_id(state.gif_id)
            if gif_path and gif_path.exists():
                return [gif_path]

        fixed_path = paths.STATE_DIR / f"{key}.gif"
        if fixed_path.exists():
            return [fixed_path]

        move_path = paths.STATE_DIR.parent / "ACTION" / "MOVE" / f"{key}.gif"
        if move_path.exists():
            return [move_path]

        return []

    # ── Actions ──

    def _on_add(self):
        from .add_dialog import AddStateDialog
        dialog = AddStateDialog(self.service, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_edit_gif(self, state_key: str):
        from .gif_gallery_dialog import GifGalleryDialog

        state = self.service.get_state(state_key)
        if not state:
            return

        gif_paths = self._get_all_gif_paths(state, state_key)
        label = state.label or state_key

        dialog = GifGalleryDialog(state_key, label, gif_paths, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        changed = False
        for filename in dialog.removed_filenames:
            if self.service.remove_gif(state_key, filename):
                changed = True
        for path in dialog.added_paths:
            if self.service.add_gif(state_key, path):
                changed = True

        if changed:
            self._populate()

    def _on_remove(self, key: str):
        if self.service.is_state_protected(key):
            QtWidgets.QMessageBox.warning(
                self, "Remove state", f"Cannot remove built-in state '{key}'."
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

    # ── Lifecycle ──

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self._cards:
            self._populate()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._gif_player.clear()
        super().closeEvent(event)


def show_state_manager(service: StateService, parent: Optional[QtWidgets.QWidget] = None):
    """Show state manager dialog."""
    dialog = StateManagerDialog(service, parent)
    dialog.exec()
