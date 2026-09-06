"""Move State Manager Dialog - manage movement and transition actions (card grid)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from ....utils import paths
from ....core.state import State, StateService
from ...components.gif_player import GifPlayer
from ...components.frameless_dialog import FramelessDialog

if TYPE_CHECKING:
    from ....core.action import ActionService


# ───────────────────────────────────────────────────────────
# Action Card Widget
# ───────────────────────────────────────────────────────────

class _ActionCard(QtWidgets.QFrame):
    """A card displaying a single movement or transition action."""

    edit_clicked = QtCore.Signal(str, str)        # (action_type, key)
    remove_clicked = QtCore.Signal(str, str)      # (action_type, key)
    manage_gifs_clicked = QtCore.Signal(str)      # transition_key

    CARD_WIDTH = 210
    PREVIEW_SIZE = 110

    def __init__(
        self,
        action_type: str,           # "movement" | "transition" | "action"
        key: str,
        gif_paths: list[Path],
        gif_player: GifPlayer,
        *,
        details: str = "",
        extra_info: str = "",
        removable: bool = True,
        title: Optional[str] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self._action_type = action_type
        self._key = key
        self._title = title or key
        self._removable = removable
        self._gif_paths = gif_paths
        self._gif_player = gif_player
        self._preview_index = 0

        self.setObjectName("actionCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setStyleSheet(
            "#actionCard { background: #ffffff; border: 1px solid rgba(232,96,156,0.25);"
            " border-radius: 12px; }"
            "#actionCard:hover { border-color: #e8609c; background: #fff8fb; }"
        )
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._build(details, extra_info)

    def _build(self, details: str, extra_info: str):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # ── Type badge ──
        badge_label_map = {"movement": "Movement", "transition": "Transition", "action": "Action"}
        badge_color_map = {
            "movement": ("rgba(46,125,50,0.12)", "#2e7d32"),
            "transition": ("rgba(192,38,110,0.12)", "#c0266e"),
            "action": ("rgba(255,143,0,0.14)", "#b25400"),
        }
        bg, fg = badge_color_map.get(self._action_type, badge_color_map["transition"])
        badge = QtWidgets.QLabel(badge_label_map.get(self._action_type, self._action_type.title()))
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(20)
        badge.setStyleSheet(
            f"background: {bg}; color: {fg};"
            " border-radius: 10px; font-size: 10px; font-weight: bold; padding: 0 8px;"
        )
        layout.addWidget(badge, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        # ── GIF preview ──
        preview_row = QtWidgets.QHBoxLayout()
        preview_row.setSpacing(2)

        self._left_btn = self._arrow_button("left")
        self._left_btn.clicked.connect(lambda: self._navigate(-1))
        preview_row.addWidget(self._left_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        self._preview = QtWidgets.QLabel()
        self._preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
        self._preview.setStyleSheet("background: #fff5fa; border-radius: 8px;")
        preview_row.addWidget(self._preview, 1, QtCore.Qt.AlignmentFlag.AlignCenter)

        self._right_btn = self._arrow_button("right")
        self._right_btn.clicked.connect(lambda: self._navigate(1))
        preview_row.addWidget(self._right_btn, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(preview_row)

        # Counter
        count = len(self._gif_paths)
        self._counter = QtWidgets.QLabel(f"1/{count}" if count > 0 else "No GIF")
        self._counter.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._counter.setStyleSheet("font-size: 11px; color: #e8609c; font-weight: 600;")
        layout.addWidget(self._counter)

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

        # ── Key label ──
        name = QtWidgets.QLabel(self._title)
        name.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 13px; font-weight: bold; color: #4a2040;")
        name.setWordWrap(True)
        layout.addWidget(name)

        # ── Details ──
        if details:
            det = QtWidgets.QLabel(details)
            det.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            det.setStyleSheet("font-size: 11px; color: #9c6b8a;")
            det.setWordWrap(True)
            layout.addWidget(det)

        if extra_info:
            info = QtWidgets.QLabel(extra_info)
            info.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            info.setStyleSheet("font-size: 10px; color: #b08da0;")
            layout.addWidget(info)

        # ── Action buttons ──
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(4)

        if self._action_type == "transition":
            gifs_btn = QtWidgets.QPushButton("GIFs")
            gifs_btn.setToolTip("Manage GIFs")
            gifs_btn.setFixedHeight(26)
            gifs_btn.setStyleSheet(self._small_btn_style())
            gifs_btn.clicked.connect(lambda: self.manage_gifs_clicked.emit(self._key))
            btn_row.addWidget(gifs_btn)

        edit_btn = QtWidgets.QPushButton("Edit")
        edit_btn.setFixedHeight(26)
        edit_btn.setStyleSheet(self._small_btn_style())
        edit_btn.clicked.connect(
            lambda: self.edit_clicked.emit(self._action_type, self._key)
        )
        btn_row.addWidget(edit_btn)

        if self._removable:
            del_btn = QtWidgets.QPushButton("Del")
            del_btn.setToolTip("Remove action")
            del_btn.setFixedHeight(26)
            del_btn.setStyleSheet(self._small_btn_danger_style())
            del_btn.clicked.connect(
                lambda: self.remove_clicked.emit(self._action_type, self._key)
            )
            btn_row.addWidget(del_btn)

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
# Move State Manager Dialog
# ───────────────────────────────────────────────────────────

class MoveStateManagerDialog(FramelessDialog):
    """Dialog for managing movement and transition actions — card grid layout."""

    def __init__(
        self,
        service: StateService,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        action_service: Optional["ActionService"] = None,
    ):
        super().__init__("Action Manager", parent)
        self.service = service
        self._action_service = action_service
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._gif_player = GifPlayer()
        self._cards: list[_ActionCard] = []
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = self.content_layout

        # Scroll area
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

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

        add_btn = QtWidgets.QPushButton("Add Action")
        add_btn.clicked.connect(self._on_add)
        button_row.addWidget(add_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def _populate(self):
        self._gif_player.clear()
        self._cards.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        cols = max(1, (self.width() - 80) // (_ActionCard.CARD_WIDTH + 14))
        idx = 0

        # Movement actions
        for key in sorted(self.service.all_move_state_keys()):
            move_state = self.service.get_move_state(key)
            if not move_state:
                continue

            gif_paths: list[Path] = []
            state = self.service.get_state(move_state.state_key)
            if state:
                gif_paths = self._get_state_gif_paths(state, move_state.state_key)

            card = _ActionCard(
                "movement", key, gif_paths, self._gif_player,
                details=f"Dir: {move_state.direction}",
                extra_info=f"Speed: {move_state.default_speed}",
                parent=self._grid_container,
            )
            card.edit_clicked.connect(self._on_edit)
            card.remove_clicked.connect(self._on_remove)
            self._grid_layout.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)
            idx += 1

        # Named actions — registry-driven: one card per registered action
        # (click, dragged, …). Only when an ActionService is wired in.
        if self._action_service is not None:
            from ....core.action.repository import CLICK_ACTION_KEY, DRAG_ACTION_KEY

            action_details = {
                CLICK_ACTION_KEY: "Wind-up GIF for [mouse:click]",
                DRAG_ACTION_KEY: "拖曳 Doro 時播放",
            }
            for action_key in self._action_service.named_action_keys():
                gif_paths = self._action_service.list_action_gif_paths(action_key)
                card = _ActionCard(
                    "action", action_key, gif_paths, self._gif_player,
                    title=self._action_service.get_action_display_name(action_key),
                    details=action_details.get(action_key, ""),
                    extra_info="(fallback active)" if not gif_paths else "",
                    removable=False,  # builtins: user can only rebind the GIF
                    parent=self._grid_container,
                )
                card.edit_clicked.connect(self._on_edit)
                self._grid_layout.addWidget(card, idx // cols, idx % cols)
                self._cards.append(card)
                idx += 1

        # Transition actions
        for key in sorted(self.service.all_transition_keys()):
            transition = self.service.get_transition(key)
            if not transition:
                continue

            gif_paths = self._get_transition_gif_paths(transition.key)

            card = _ActionCard(
                "transition", key, gif_paths, self._gif_player,
                details=f"{transition.from_state} \u2192 {transition.to_state}",
                parent=self._grid_container,
            )
            card.edit_clicked.connect(self._on_edit)
            card.remove_clicked.connect(self._on_remove)
            card.manage_gifs_clicked.connect(self._on_manage_transition_gifs)
            self._grid_layout.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)
            idx += 1

    # ── GIF path helpers ──

    def _get_state_gif_paths(self, state: State, key: str) -> list[Path]:
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

    def _get_transition_gif_paths(self, transition_key: str) -> list[Path]:
        gif_paths = self.service.list_transition_gif_paths(transition_key)
        if gif_paths:
            return gif_paths
        transition = self.service.get_transition(transition_key)
        if transition and transition.transition_gif_id:
            gif_path = paths.ACTION_TRANSITION_DIR / transition.transition_gif_id
            if gif_path.exists():
                return [gif_path]
        return []

    # ── Actions ──

    def _on_add(self):
        from .edit_dialog import EditMoveStateDialog
        dialog = EditMoveStateDialog(
            self.service, None, self, action_service=self._action_service,
        )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_edit(self, action_type: str, key: str):
        from .edit_dialog import EditMoveStateDialog
        if action_type == "action":
            dialog = EditMoveStateDialog(
                self.service, None, self,
                action_service=self._action_service,
                edit_action_key=key,
            )
        else:
            dialog = EditMoveStateDialog(
                self.service, key, self, action_service=self._action_service,
            )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._populate()

    def _on_remove(self, action_type: str, key: str):
        action_type_text = "movement" if action_type == "movement" else "transition"
        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove action",
            f"Remove {action_type_text} '{key}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._gif_player.clear()
            self._cards.clear()

            try:
                if action_type == "movement":
                    success = self.service.remove_move_state(key)
                else:
                    success = self.service.remove_transition(key)
            except Exception:
                success = True

            if success:
                self._populate()
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Remove action", f"Failed to remove {action_type_text}."
                )

    def _on_manage_transition_gifs(self, key: str):
        from ..state.gif_gallery_dialog import GifGalleryDialog

        gif_paths = self._get_transition_gif_paths(key)
        dialog = GifGalleryDialog(key, key, gif_paths, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            removed = dialog.removed_filenames
            added = dialog.added_paths
            dialog.cleanup()
            self._gif_player.clear()
            self._cards.clear()

            for filename in removed:
                try:
                    self.service.remove_transition_gif(key, filename)
                except Exception:
                    pass
            for path in added:
                self.service.add_transition_gif(key, path)
            self._populate()

    # ── Lifecycle ──

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self._cards:
            self._populate()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._gif_player.clear()
        super().closeEvent(event)


def show_move_state_manager(
    service: StateService,
    parent: Optional[QtWidgets.QWidget] = None,
    *,
    action_service: Optional["ActionService"] = None,
):
    """Show movement state manager dialog."""
    dialog = MoveStateManagerDialog(service, parent, action_service=action_service)
    dialog.exec()
