"""Companion preferences with staged GIF import and per-file foot calibration."""

from pathlib import Path
from uuid import uuid4

from PySide6 import QtCore, QtGui, QtWidgets


class FootPreview(QtWidgets.QWidget):
    ratio_changed = QtCore.Signal(float)

    def __init__(self, pixmap, ratio, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.ratio = ratio
        self.setMinimumSize(260, 190)
        self.setToolTip("點擊圖片設定腳底線，也可用下方數值微調")

    def image_rect(self):
        size = self.pixmap.size().scaled(
            self.size() - QtCore.QSize(24, 24), QtCore.Qt.AspectRatioMode.KeepAspectRatio
        )
        return QtCore.QRect(
            (self.width() - size.width()) // 2,
            (self.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#f9edf3"))
        rect = self.image_rect()
        painter.drawPixmap(rect, self.pixmap)
        painter.setPen(QtGui.QPen(QtGui.QColor("#b83268"), 2, QtCore.Qt.PenStyle.DashLine))
        y = rect.top() + round((rect.height() - 1) * self.ratio)
        painter.drawLine(rect.left(), y, rect.right(), y)

    def mousePressEvent(self, event):
        rect = self.image_rect()
        if event.button() == QtCore.Qt.MouseButton.LeftButton and rect.contains(
            event.position().toPoint()
        ):
            self.ratio_changed.emit(
                max(0, min(1, (event.position().y() - rect.top()) / max(1, rect.height() - 1)))
            )


class CompanionDialog(QtWidgets.QDialog):
    def __init__(self, config, states, window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("陪伴設定")
        self.setMinimumWidth(450)
        self._config, self._states, self._window = config, states, window
        self._pending_gif = None
        self._movie = None
        self._gif_key = window.current_gif_key()
        self._anchor_changed = False
        self._anchor_reset = False
        root = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        root.addWidget(tabs)
        page = QtWidgets.QWidget()
        tabs.addTab(page, "陪伴與休息")
        layout = QtWidgets.QVBoxLayout(page)
        intro = QtWidgets.QLabel("讓她有自己的小節奏，忙碌時仍能安靜陪你。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QtWidgets.QFormLayout()
        self.interval = QtWidgets.QSpinBox()
        self.interval.setRange(1, 3600)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(config.ui.companion_interval_seconds)
        form.addRow("活動間隔", self.interval)
        interval_hint = QtWidgets.QLabel(
            "非安靜時每隔幾秒嘗試活動；聊天、拖曳或動作未結束時會延後。"
        )
        interval_hint.setWordWrap(True)
        form.addRow(interval_hint)
        self.effects = QtWidgets.QCheckBox("小動作與摸摸愛心（安靜時也會偶爾伸展）")
        self.effects.setChecked(config.ui.companion_effects)
        form.addRow(self.effects)
        self.rest_state = QtWidgets.QComboBox()
        for key in states.visible_state_keys():
            state = states.get_state(key)
            if state and not states.is_movement_only_state(key):
                self.rest_state.addItem(state.label or key, key)
        self.rest_state.setCurrentIndex(
            max(0, self.rest_state.findData(config.ui.companion_rest_state))
        )
        form.addRow("休息姿勢", self.rest_state)
        layout.addLayout(form)
        self.preview = QtWidgets.QLabel()
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(140)
        self.preview.setStyleSheet("background: #f9edf3; border-radius: 12px;")
        layout.addWidget(self.preview)
        self.import_button = QtWidgets.QPushButton("匯入休息 GIF…")
        self.import_button.clicked.connect(self._choose_gif)
        layout.addWidget(self.import_button)
        self.rest_state.currentIndexChanged.connect(self._preview_state)
        self._preview_state()

        self.anchor = None
        movie = getattr(window.sprite_renderer, "base_movie", None) if self._gif_key else None
        pixmap = movie.currentPixmap() if movie is not None else None
        if pixmap is not None and not pixmap.isNull():
            group = QtWidgets.QGroupBox("目前 GIF 的腳底校正")
            box = QtWidgets.QVBoxLayout(group)
            description = QtWidgets.QLabel(
                f"{Path(self._gif_key).name}\n把虛線放在腳掌接觸的位置；會套用到這個 GIF。"
            )
            description.setWordWrap(True)
            box.addWidget(description)
            auto_bounds = window.sprite_renderer.contact_bounds()
            self._auto_ratio = auto_bounds.bottom() / max(1, pixmap.height() - 1)
            ratio = config.ui.sprite_foot_overrides.get(self._gif_key, self._auto_ratio)
            self.foot_preview = FootPreview(pixmap, ratio)
            box.addWidget(self.foot_preview)
            row = QtWidgets.QHBoxLayout()
            self.anchor = QtWidgets.QDoubleSpinBox()
            self.anchor.setRange(0, 100)
            self.anchor.setDecimals(1)
            self.anchor.setSuffix(" %")
            self.anchor.setValue(ratio * 100)
            self.anchor.valueChanged.connect(self._anchor_value)
            self.foot_preview.ratio_changed.connect(lambda value: self.anchor.setValue(value * 100))
            row.addWidget(self.anchor)
            reset = QtWidgets.QPushButton("還原自動估計")
            reset.clicked.connect(self._reset_anchor)
            row.addWidget(reset)
            box.addLayout(row)
            tabs.addTab(group, "腳底校正")
        poses_page = QtWidgets.QWidget()
        poses_layout = QtWidgets.QVBoxLayout(poses_page)
        poses_hint = QtWidgets.QLabel("只會自主播放勾選的姿勢。全部取消時仍可散步與做小動作。")
        poses_hint.setWordWrap(True)
        poses_layout.addWidget(poses_hint)
        self.pose_list = QtWidgets.QListWidget()
        for key in states.visible_state_keys():
            state = states.get_state(key)
            if state and not states.is_movement_only_state(key):
                item = QtWidgets.QListWidgetItem(state.label or key, self.pose_list)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    QtCore.Qt.CheckState.Checked
                    if key in config.ui.companion_pose_keys
                    else QtCore.Qt.CheckState.Unchecked
                )
        poses_layout.addWidget(self.pose_list)
        tabs.addTab(poses_page, "自主姿勢")
        hint = QtWidgets.QLabel("休息點仍可放在螢幕任意位置；底部下落功能維持停用。")
        hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("儲存")
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        root.addWidget(buttons)

    def _anchor_value(self, value):
        self._anchor_changed = True
        self._anchor_reset = False
        self.foot_preview.ratio = value / 100
        self.foot_preview.update()

    def _reset_anchor(self):
        self.anchor.setValue(self._auto_ratio * 100)
        self._anchor_changed = True
        self._anchor_reset = True

    def _preview_state(self):
        self._pending_gif = None
        key = self.rest_state.currentData()
        self._load_preview(self._states.get_gif_path(key) if key else None)

    def _load_preview(self, path):
        self.cleanup()
        if not path:
            self.preview.setText("這個姿勢尚未設定 GIF")
            return False
        movie = QtGui.QMovie(str(path))
        if not movie.isValid():
            movie.deleteLater()
            self.preview.setText("無法讀取這個 GIF")
            return False
        movie.jumpToFrame(0)
        movie.setScaledSize(
            movie.frameRect().size().scaled(220, 140, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        )
        self._movie = movie
        self.preview.setMovie(movie)
        movie.start()
        return True

    def _choose_gif(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "選擇休息 GIF", "", "GIF (*.gif)")
        if path:
            self._pending_gif = None
            if self._load_preview(path):
                self._pending_gif = Path(path)
            else:
                QtWidgets.QMessageBox.warning(
                    self, "匯入失敗", "無法讀取這個 GIF，請選擇有效的檔案。"
                )

    def accept(self):
        key = self.rest_state.currentData() or "idle"
        if self._pending_gif:
            self.cleanup()  # Release the preview file handle before copying on Windows.
            key = "rest_" + uuid4().hex[:8]
            if not self._states.add_state(key, "休息 · " + self._pending_gif.stem):
                QtWidgets.QMessageBox.warning(self, "匯入失敗", "無法建立休息姿勢，請稍後再試。")
                return
            if not self._states.set_gif(key, self._pending_gif):
                self._states.remove_state(key)
                QtWidgets.QMessageBox.warning(self, "匯入失敗", "GIF 未能儲存，請換一個檔案再試。")
                return
        anchors = dict(self._config.ui.sprite_foot_overrides)
        if self._anchor_changed:
            if self._anchor_reset:
                anchors.pop(self._gif_key, None)
            else:
                anchors[self._gif_key] = self.anchor.value() / 100
        self._config.update_ui(
            companion_interval_seconds=self.interval.value(),
            companion_effects=self.effects.isChecked(),
            companion_rest_state=key,
            companion_pose_keys=[
                self.pose_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
                for i in range(self.pose_list.count())
                if self.pose_list.item(i).checkState() == QtCore.Qt.CheckState.Checked
            ],
            sprite_foot_overrides=anchors,
        )
        self._config.save()
        self._window.clear_expression()
        self._window.apply_window_preferred_size()
        self.cleanup()
        super().accept()

    def reject(self):
        self.cleanup()
        super().reject()

    def cleanup(self):
        self.preview.clear()
        if self._movie is not None:
            self._movie.stop()
            self._movie.setFileName("")
            self._movie.deleteLater()
            self._movie = None
