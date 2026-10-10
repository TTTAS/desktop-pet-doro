"""GIF Gallery Dialog - view and manage all GIFs for a state."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...components.frameless_dialog import FramelessDialog
from ...components.gif_player import GifPlayer


class GifThumbnail(QtWidgets.QFrame):
    """A single GIF thumbnail with delete button overlay."""

    remove_clicked = QtCore.Signal(str)  # filename

    def __init__(
        self,
        gif_path: Path,
        gif_player: GifPlayer,
        removable: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.gif_path = gif_path
        self._removable = removable
        self.setObjectName("gifThumb")
        self.setFixedSize(180, 210)
        self.setStyleSheet(
            "#gifThumb { background: #ffffff; border: 1px solid rgba(232,96,156,0.30); border-radius: 6px; }"
            "#gifThumb:hover { border-color: #e8609c; }"
        )
        self._setup_ui(gif_player)

    def _setup_ui(self, gif_player: GifPlayer):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # GIF preview
        preview = QtWidgets.QLabel()
        preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        preview.setFixedSize(170, 175)
        movie = gif_player.load(self.gif_path, size=QtCore.QSize(160, 160))
        if movie:
            preview.setMovie(movie)
        else:
            preview.setText("?")
            preview.setStyleSheet("color: #9c6b8a;")
        layout.addWidget(preview, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        # Delete button overlay (top-right corner of the frame)
        if self._removable:
            del_btn = QtWidgets.QPushButton("X", self)
            del_btn.setFixedSize(20, 20)
            del_btn.setToolTip("Remove this GIF")
            del_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton { background: #c62828; color: white; border: none;"
                " border-radius: 10px; font-size: 11px; font-weight: bold;"
                " padding: 0px; margin: 0px; }"
                "QPushButton:hover { background: #ff5252; }"
            )
            del_btn.move(self.width() - 24, 4)
            del_btn.raise_()
            del_btn.clicked.connect(lambda: self.remove_clicked.emit(self.gif_path.name))
            self._del_btn = del_btn

        # Filename label
        name_label = QtWidgets.QLabel(self.gif_path.name)
        name_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #4a2040; border: none;"
        )
        name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        name_label.setToolTip(self.gif_path.name)
        metrics = name_label.fontMetrics()
        elided = metrics.elidedText(self.gif_path.name, QtCore.Qt.TextElideMode.ElideMiddle, 168)
        name_label.setText(elided)
        layout.addWidget(name_label)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self._removable and hasattr(self, "_del_btn"):
            self._del_btn.move(self.width() - 24, 4)


class GifGalleryDialog(FramelessDialog):
    """
    Dialog showing all GIFs for a state in a grid layout.

    Allows adding new GIFs and removing existing ones.
    """

    def __init__(
        self,
        state_key: str,
        state_label: str,
        gif_paths: list[Path],
        parent: QtWidgets.QWidget | None = None,
        *,
        allow_empty: bool = False,
    ):
        super().__init__(f"GIF Gallery - {state_label}", parent)
        self.state_key = state_key
        self._allow_empty = allow_empty
        self._gif_paths = list(gif_paths)
        self._gif_player = GifPlayer()
        self._added: list[Path] = []  # GIFs to add
        self._removed: list[str] = []  # filenames to remove
        self._thumbnails: list[GifThumbnail] = []

        self.setMinimumWidth(500)
        self.setMinimumHeight(320)
        self._setup_ui()
        self._refresh_grid()

    @property
    def added_paths(self) -> list[Path]:
        return list(self._added)

    @property
    def removed_filenames(self) -> list[str]:
        return list(self._removed)

    def _setup_ui(self):
        layout = self.content_layout

        # Header
        header = QtWidgets.QHBoxLayout()

        header.addStretch()

        self._count_label = QtWidgets.QLabel()
        self._count_label.setStyleSheet("font-size: 12px; color: #9c6b8a;")
        header.addWidget(self._count_label)

        layout.addLayout(header)

        # Scroll area for GIF grid
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid rgba(232,96,156,0.25); border-radius: 6px; background: #fff5fa; }"
        )

        self._grid_container = QtWidgets.QWidget()
        self._grid_container.setStyleSheet("background: #fff5fa;")
        self._grid_layout = QtWidgets.QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()

        add_btn = QtWidgets.QPushButton("+ Add GIF(s)")
        add_btn.setStyleSheet(
            "QPushButton { background: #2e7d32; color: white; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #388e3c; }"
        )
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)

        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def _refresh_grid(self):
        """Rebuild the thumbnail grid from current state."""
        # Clear existing
        self._gif_player.clear()
        self._thumbnails.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        # Build the effective list: original minus removed, plus added
        effective: list[tuple[Path, bool]] = []  # (path, is_new)

        for p in self._gif_paths:
            if p.name not in self._removed:
                effective.append((p, False))

        for p in self._added:
            effective.append((p, True))

        # Calculate columns based on dialog width
        cols = max(1, (self.width() - 52) // 190)

        for i, (path, is_new) in enumerate(effective):
            # All existing GIFs are removable; new ones are also removable
            thumb = GifThumbnail(
                path, self._gif_player, removable=True, parent=self._grid_container
            )
            if is_new:
                # Highlight new additions with a green border
                thumb.setStyleSheet(
                    "#gifThumb { background: #ffffff; border: 2px solid #2e7d32; border-radius: 6px; }"
                    "#gifThumb:hover { border-color: #4caf50; }"
                )
            thumb.remove_clicked.connect(self._on_remove_gif)
            self._grid_layout.addWidget(thumb, i // cols, i % cols)
            self._thumbnails.append(thumb)

        # Update count
        total = len(effective)
        self._count_label.setText(f"{total} GIF(s)")

    def _on_add(self):
        """Open file picker to add GIF(s)."""
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select GIF file(s)",
            "",
            "Animated Images (*.gif *.apng *.webp);;All Files (*.*)",
        )
        if not file_paths:
            return

        for fp in file_paths:
            self._added.append(Path(fp))

        self._refresh_grid()

    def _on_remove_gif(self, filename: str):
        """Handle remove click on a thumbnail."""
        # Check if it's a newly added GIF
        for i, p in enumerate(self._added):
            if p.name == filename:
                self._added.pop(i)
                self._refresh_grid()
                return

        # It's an existing GIF - mark for removal
        # Check how many will remain
        remaining_original = sum(
            1 for p in self._gif_paths if p.name not in self._removed and p.name != filename
        )
        remaining_new = len(self._added)
        total_remaining = remaining_original + remaining_new

        if total_remaining == 0 and not self._allow_empty:
            QtWidgets.QMessageBox.warning(self, "Cannot remove", "At least one GIF must remain.")
            return

        self._removed.append(filename)
        self._refresh_grid()

    def resizeEvent(self, event: QtGui.QResizeEvent):
        """Reflow grid on resize."""
        super().resizeEvent(event)
        if self._thumbnails:
            self._refresh_grid()

    def cleanup(self) -> None:
        """Release GIF file handles (call before deleting GIF files)."""
        self._gif_player.clear()

    def done(self, result: int) -> None:
        self.cleanup()
        super().done(result)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.cleanup()
        super().closeEvent(event)


def apply_gallery_changes(dialog, parent, release_previews, remove_gif, add_gif) -> None:
    """Release every caller-owned preview before writing; report unsuccessful edits."""
    removed, added = dialog.removed_filenames, dialog.added_paths
    dialog.cleanup()
    release_previews()
    failures = []
    for items, operation, label in (
        (removed, remove_gif, "刪除"),
        (added, add_gif, "新增"),
    ):
        for item in items:
            try:
                if not operation(item):
                    failures.append(f"{label} {Path(item).name}：未成功")
            except Exception as exc:
                failures.append(f"{label} {Path(item).name}：{exc}")
    if failures:
        QtWidgets.QMessageBox.warning(parent, "部分 GIF 變更未完成", "\n".join(failures))
