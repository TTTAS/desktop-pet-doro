"""Doro2's local media pipeline, presented in Doro's Qt interface."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from ...core.gif_factory.config import load_config, save_config
from ...core.gif_factory.frames import ANIMATED_IMAGE_SUFFIXES, extract_frames, is_animated_image
from ...core.gif_factory.matting import MattingOptions, remove_background
from ...core.gif_factory.output import DoroSpec, apply_doro_layout, body_bounds, save_image
from ...core.gif_factory.pipeline import (
    available_output_path,
    check_cancelled,
    doro_layout_for_frame,
    frame_layout_is_exact,
    process_video,
)
from ...core.gif_factory.preview import composite_on_checker, fit_within, overlay_doro_reference
from ...utils.paths import STATE_DIR
from ..components.frameless_dialog import FramelessDialog

# 預覽「對齊 Doro 規格」時疊在後面的半透明參考 Doro。
_DORO_REFERENCE_PATH = STATE_DIR / "stand.gif"

_OPEN_FILTER = (
    "影片或動圖 (*.mp4 "
    + " ".join(f"*{suffix}" for suffix in sorted(ANIMATED_IMAGE_SUFFIXES))
    + ");;MP4 影片 (*.mp4);;GIF 動圖 (*.gif);;所有檔案 (*)"
)


class MediaJob(QtCore.QThread):
    """Only plain image/file data crosses the worker boundary."""

    progress = QtCore.Signal(int, str)
    exported = QtCore.Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel = Event()
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation(self)
            check_cancelled(self.cancel)
        except Exception as exc:
            self.error = exc


class SourcePreview(QtWidgets.QLabel):
    color_picked = QtCore.Signal(object)

    def __init__(self):
        super().__init__("選擇影片或 GIF 後顯示原圖；顏色模式可點圖取色")
        self.source = None
        self.scale = 1.0
        self.setFixedSize(300, 260)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        pixmap = self.pixmap()
        if self.source is not None and pixmap and not pixmap.isNull():
            x = event.position().x() - (self.width() - pixmap.width()) / 2
            y = event.position().y() - (self.height() - pixmap.height()) / 2
            if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
                self.color_picked.emit(
                    self.source.convert("RGB").getpixel(
                        (
                            min(self.source.width - 1, int(x / self.scale)),
                            min(self.source.height - 1, int(y / self.scale)),
                        )
                    )
                )
        super().mousePressEvent(event)


def _load_doro_reference():
    """回傳 (參考 Doro 第一格, 角色本體高度);讀不到時回傳 (None, None),預覽只畫腳底線。"""
    try:
        with Image.open(_DORO_REFERENCE_PATH) as image:
            reference = image.convert("RGBA")
    except (OSError, ValueError):
        return None, None
    bounds = body_bounds([reference])
    return reference, (bounds[3] - bounds[1]) if bounds else None


def _place_frame(frames, rgba, options, spec):
    """預覽與單格 PNG 共用:算出變換並套到這一格,兩者結果才一致。"""
    layout = doro_layout_for_frame(frames, rgba, options, spec)
    return apply_doro_layout([rgba], layout, spec.canvas)[0], layout


def _pixmap(image):
    rgba = image.convert("RGBA")
    qimage = QtGui.QImage(
        rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QtGui.QImage.Format.Format_RGBA8888
    ).copy()
    return QtGui.QPixmap.fromImage(qimage)


class AssetFactoryDialog(FramelessDialog):
    """Serial jobs and queued Qt signals keep all widget changes on the GUI thread."""

    def __init__(self, state_service, parent=None):
        super().__init__("素材工廠 · 影片／GIF 去背", parent)
        self.service = state_service
        self._job = None
        self._frames = []
        self._paths = []
        self._loaded_path = None
        self._color = (255, 255, 255)
        self._close_pending = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._preview)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout
        self.controls = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(self.controls)
        form.setContentsMargins(0, 0, 0, 0)
        choose = QtWidgets.QPushButton("選擇 MP4 影片或 GIF 動圖（可多選）…")
        choose.clicked.connect(self._choose)
        form.addWidget(choose)
        self.videos = QtWidgets.QComboBox()
        self.videos.currentIndexChanged.connect(self._load_video)
        form.addWidget(self.videos)
        previews = QtWidgets.QHBoxLayout()
        self.source = SourcePreview()
        self.source.color_picked.connect(self._pick_color)
        self.preview = QtWidgets.QLabel("去背預覽（棋盤格代表透明）")
        self.preview.setFixedSize(300, 260)
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        previews.addWidget(self.source)
        previews.addWidget(self.preview)
        form.addLayout(previews)
        self.frame_label = QtWidgets.QLabel("尚未讀取影片")
        form.addWidget(self.frame_label)
        self.frame = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.frame.setRange(0, 0)
        self.frame.valueChanged.connect(self._frame_changed)
        form.addWidget(self.frame)
        options = QtWidgets.QFormLayout()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItem("AI 去背（isnet-anime）", "ai")
        self.mode.addItem("顏色去背（點左圖取色）", "color")
        self.mode.addItem("不去背（保留原圖透明）", "none")
        self.mode.currentIndexChanged.connect(self._schedule_preview)
        options.addRow("去背方式", self.mode)
        self.color_label = QtWidgets.QLabel("取色：255, 255, 255")
        options.addRow(self.color_label)
        self.tolerance = QtWidgets.QSpinBox()
        self.tolerance.setRange(0, 442)
        self.tolerance.setValue(30)
        self.tolerance.valueChanged.connect(self._schedule_preview)
        options.addRow("顏色容差", self.tolerance)
        self.edge_only = QtWidgets.QCheckBox(
            "只去除與邊緣相連的背景（保留角色身上的同色，例如白底白身體）"
        )
        self.edge_only.setChecked(True)
        self.edge_only.toggled.connect(self._schedule_preview)
        options.addRow(self.edge_only)
        self.erode = QtWidgets.QSpinBox()
        self.erode.setRange(0, 20)
        self.erode.valueChanged.connect(self._schedule_preview)
        options.addRow("邊緣內縮（像素）", self.erode)
        self.soft = QtWidgets.QCheckBox("AI 邊緣柔化")
        self.soft.toggled.connect(self._schedule_preview)
        options.addRow(self.soft)
        config = load_config()
        self.fmt = QtWidgets.QComboBox()
        self.fmt.addItems(["webp", "apng", "gif"])
        self.fmt.setCurrentText(str(config.get("fmt", "webp")))
        options.addRow("動畫格式", self.fmt)
        self.size_mode = QtWidgets.QComboBox()
        self.size_mode.addItem("維持原尺寸", "original")
        self.size_mode.addItem("縮小長邊（只縮不放）", "shrink")
        self.size_mode.addItem("統一 N×N 畫布（可放大、底部置中）", "canvas")
        self.size_mode.addItem("對齊 Doro 規格（裁留白、腳踩同一條線）", "doro")
        legacy_mode = "shrink" if config.get("resize", True) else "original"
        index = self.size_mode.findData(config.get("size_mode", legacy_mode))
        self.size_mode.setCurrentIndex(index if index >= 0 else 1)
        self.size_mode.currentIndexChanged.connect(self._size_mode_changed)
        self.size = QtWidgets.QSpinBox()
        self.size.setRange(1, 8192)
        try:
            self.size.setValue(int(config.get("output_size", 200)))
        except (ValueError, TypeError):
            self.size.setValue(200)
        self.body_height = QtWidgets.QSpinBox()
        self.body_height.setRange(1, DoroSpec.foot_y)
        self.body_height.setPrefix("身高 ")
        self.body_height.setToolTip("角色本體高度；Doro 站姿約 170、待機約 150，坐姿或趴姿可調低")
        try:
            self.body_height.setValue(int(config.get("doro_body_height", DoroSpec.body_height)))
        except (ValueError, TypeError):
            self.body_height.setValue(DoroSpec.body_height)
        self.body_height.valueChanged.connect(self._schedule_preview)
        size_row = QtWidgets.QHBoxLayout()
        size_row.addWidget(self.size_mode, 1)
        size_row.addWidget(self.size)
        size_row.addWidget(self.body_height)
        options.addRow("輸出尺寸（像素）", size_row)
        self._size_mode_changed()
        output_row = QtWidgets.QHBoxLayout()
        self.output_dir = QtWidgets.QLineEdit(str(config.get("output_dir", Path.home())))
        browse = QtWidgets.QPushButton("瀏覽…")
        browse.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_dir)
        output_row.addWidget(browse)
        options.addRow("輸出資料夾", output_row)
        form.addLayout(options)
        buttons = QtWidgets.QHBoxLayout()
        self.animate = QtWidgets.QPushButton("處理全部檔案")
        self.animate.clicked.connect(self._export_animation)
        self.still = QtWidgets.QPushButton("這一格存成 PNG")
        self.still.clicked.connect(self._export_frame)
        buttons.addWidget(self.animate)
        buttons.addWidget(self.still)
        form.addLayout(buttons)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.controls)
        scroll.setMinimumWidth(650)
        scroll.setMinimumHeight(420)
        layout.addWidget(scroll, 1)
        self.resize(730, 820)
        self.progress = QtWidgets.QProgressBar()
        layout.addWidget(self.progress)
        self.status = QtWidgets.QLabel("全程本機處理；首次 AI 去背需下載模型。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QtWidgets.QListWidget()
        self.results.setMaximumHeight(85)
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.results)
        self.import_controls = QtWidgets.QWidget()
        imports = QtWidgets.QHBoxLayout(self.import_controls)
        imports.setContentsMargins(0, 0, 0, 0)
        self.target = QtWidgets.QComboBox()
        self.target.addItem("建立新姿勢…", None)
        for key in self.service.visible_state_keys():
            state = self.service.get_state(key)
            self.target.addItem(state.label or key, key)
        imports.addWidget(self.target)
        import_button = QtWidgets.QPushButton("將選取動畫匯入姿勢")
        import_button.clicked.connect(self._import_selected)
        imports.addWidget(import_button)
        layout.addWidget(self.import_controls)
        self.cancel_button = QtWidgets.QPushButton("取消處理")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_button)
        self._set_busy(False)

    def _set_busy(self, busy):
        self.controls.setEnabled(not busy)
        self.import_controls.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.animate.setEnabled(bool(self._frames))
        self.still.setEnabled(bool(self._frames))

    def _start_job(self, operation, completed):
        if self._job is not None:
            return
        self._timer.stop()
        self._set_busy(True)
        self.progress.setValue(0)
        self._job = MediaJob(operation, self)
        self._completed = completed
        self._job.progress.connect(self._progress)
        self._job.exported.connect(self._add_result)
        self._job.finished.connect(self._job_finished)
        self._job.start()

    @QtCore.Slot(int, str)
    def _progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    @QtCore.Slot()
    def _job_finished(self):
        job = self._job
        self._job = None
        self._set_busy(False)
        if self._close_pending:
            job.deleteLater()
            super().reject()
            return
        if job.error:
            message = str(job.error)
            if isinstance(job.error, ImportError):
                message += '\nAI 去背請先執行：python -m pip install -e ".[factory-ai]"'
            self.status.setText(message)
        else:
            self._completed(job.result)
        job.deleteLater()

    def _cancel(self):
        if self._job:
            self._job.cancel.set()
            self.status.setText("正在取消，等待目前影格或編碼完成…")

    def reject(self):
        self._timer.stop()
        if self._job:
            self._close_pending = True
            self._cancel()
        else:
            super().reject()

    def closeEvent(self, event):
        if self._job:
            self.reject()
            event.ignore()
        else:
            self._timer.stop()
            super().closeEvent(event)

    def shutdown(self):
        """Also protect worker lifetime if QApplication exits during dialog.exec()."""
        self._timer.stop()
        if self._job:
            self._job.cancel.set()
            self._job.wait()

    def _choose(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "選擇影片或動圖", "", _OPEN_FILTER)
        if paths:
            self._paths = [Path(p) for p in paths]
            if all(is_animated_image(p) for p in self._paths):
                # 網路上的 GIF 多半已經去好背，預設只轉格式／統一大小。
                self.mode.setCurrentIndex(self.mode.findData("none"))
            self.videos.blockSignals(True)
            self.videos.clear()
            self.videos.addItems([p.name for p in self._paths])
            self.videos.blockSignals(False)
            self._load_video(0)

    def _load_video(self, index):
        if index < 0 or self._job:
            return
        path = self._paths[index]
        self._frames = []
        self._loaded_path = None
        self.source.source = None
        self.source.clear()
        self.preview.clear()
        self.status.setText(f"正在讀取 {path.name}…")

        def loaded(video):
            self._frames = video.frames
            self._loaded_path = path
            self.frame.setRange(0, len(video.frames) - 1)
            self.frame.setValue(len(video.frames) // 2)
            self._set_busy(False)
            self._frame_changed()

        self._start_job(lambda job: extract_frames(path, cancel=job.cancel), loaded)

    def _frame_changed(self, *_):
        if not self._frames:
            return
        image = self._frames[self.frame.value()]
        small, scale = fit_within(image, 250)
        self.source.source, self.source.scale = image, scale
        self.source.setPixmap(_pixmap(small))
        self.frame_label.setText(f"第 {self.frame.value() + 1} / {len(self._frames)} 格")
        self._schedule_preview()

    def _pick_color(self, color):
        if self.mode.currentData() == "color":
            self._color = color
            self.color_label.setText("取色：" + ", ".join(map(str, color)))
            self._schedule_preview()

    def _size_mode_changed(self, *_):
        mode = self.size_mode.currentData()
        self.size.setVisible(mode != "doro")
        self.size.setEnabled(mode != "original")
        self.body_height.setVisible(mode == "doro")
        self._schedule_preview()

    def _schedule_preview(self, *_):
        mode = self.mode.currentData()
        self.tolerance.setEnabled(mode == "color")
        self.edge_only.setEnabled(mode == "color")
        self.soft.setEnabled(mode == "ai")
        if self._frames and not self._job:
            self._timer.start()

    def _doro_spec(self):
        if self.size_mode.currentData() != "doro":
            return None
        return DoroSpec(body_height=self.body_height.value())

    def _options(self):
        return MattingOptions(
            mode=self.mode.currentData(),
            color_key=self._color,
            tolerance=self.tolerance.value(),
            edge_only=self.edge_only.isChecked(),
            erode=self.erode.value(),
            alpha_matting=self.soft.isChecked(),
        )

    def _preview(self):
        if not self._frames or self._job:
            return
        image, options, spec = self._frames[self.frame.value()], self._options(), self._doro_spec()
        frames = list(self._frames)
        self.preview.clear()
        self.status.setText("去背預覽中；首次 AI 去背可能需要下載模型…")

        def operation(job):
            rgba = remove_background(image, options)
            if spec is None:
                return rgba, None
            placed, layout = _place_frame(frames, rgba, options, spec)
            reference, reference_height = _load_doro_reference()
            scale = spec.body_height / reference_height if reference_height else 1.0
            preview = overlay_doro_reference(placed, reference, spec.foot_y, reference_scale=scale)
            return preview, layout

        def completed(result):
            rgba, layout = result
            small, _ = fit_within(rgba, 250)
            self.preview.setPixmap(_pixmap(composite_on_checker(small)))
            if spec is None:
                self.status.setText("預覽完成；可調整設定或輸出。")
                return
            notes = []
            if not frame_layout_is_exact(options):
                notes.append("大小以目前這格估算，整支輸出時會以全部影格重算")
            elif layout is not None and layout.clipped_frames:
                notes.append(f"有 {layout.clipped_frames} 格動作超出畫布，輸出時會被裁掉")
            suffix = "（" + "；".join(notes) + "）" if notes else ""
            self.status.setText(f"預覽完成：淡色為同身高的參考 Doro、紅線為腳底{suffix}。")

        self._start_job(operation, completed)

    def _choose_output(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "輸出資料夾", self.output_dir.text()
        )
        if path:
            self.output_dir.setText(path)

    def _export_settings(self):
        if not self.output_dir.text().strip():
            self.status.setText("請選擇輸出資料夾。")
            return None
        folder = Path(self.output_dir.text().strip()).expanduser()
        size_mode = self.size_mode.currentData()
        layout = {
            "size": None if size_mode in ("original", "doro") else self.size.value(),
            "canvas": size_mode == "canvas",
            "doro": self._doro_spec(),
        }
        try:
            save_config(
                {
                    "output_dir": str(folder),
                    "fmt": self.fmt.currentText(),
                    "resize": size_mode != "original",  # DORO2 仍讀這個欄位
                    "size_mode": size_mode,
                    "output_size": self.size.value(),
                    "doro_body_height": self.body_height.value(),
                }
            )
        except OSError:
            pass  # Export remains available when preferences cannot be written.
        return folder, layout

    def _export_animation(self):
        settings = self._export_settings()
        if not settings or not self._frames or self._job:
            return
        folder, layout = settings
        paths, fmt, options = list(self._paths), self.fmt.currentText(), self._options()
        self.status.setText("處理檔案中…")

        def operation(job):
            clipped = []

            def report(layout, name):
                if layout is not None and layout.clipped_frames:
                    clipped.append(f"{name} {layout.clipped_frames} 格")

            for index, path in enumerate(paths):
                check_cancelled(job.cancel)
                output = available_output_path(folder / f"{path.stem}.{fmt}")

                def progress(done, total, file_index=index, name=path.name):
                    job.progress.emit(
                        int(100 * (file_index + done / total) / len(paths)),
                        f"{file_index + 1}/{len(paths)} · {name} · {done}/{total} 格",
                    )

                result = process_video(
                    path,
                    output,
                    fmt=fmt,
                    options=options,
                    progress=progress,
                    cancel=job.cancel,
                    on_layout=lambda doro_layout, name=path.name: report(doro_layout, name),
                    **layout,
                )
                job.exported.emit(str(result))
            return clipped

        def completed(clipped):
            message = "輸出完成，可選取動畫匯入姿勢。"
            if clipped:
                message += "注意：動作超出畫布已裁掉（" + "、".join(clipped) + "）。"
            self.status.setText(message)

        self._start_job(operation, completed)

    def _export_frame(self):
        settings = self._export_settings()
        if not settings or not self._frames or self._job:
            return
        folder, layout = settings
        image, options, frames = (
            self._frames[self.frame.value()],
            self._options(),
            list(self._frames),
        )
        output = available_output_path(
            folder / f"{self._loaded_path.stem}_frame{self.frame.value() + 1}.png"
        )
        self.status.setText("正在輸出 PNG…")

        def operation(job):
            rgba = remove_background(image, options)
            check_cancelled(job.cancel)
            spec = layout["doro"]
            if spec is not None:
                rgba, _ = _place_frame(frames, rgba, options, spec)
            result = save_image(rgba, output, size=layout["size"], canvas=layout["canvas"])
            job.exported.emit(str(result))

        self._start_job(operation, lambda _: self.status.setText("PNG 已儲存。"))

    @QtCore.Slot(str)
    def _add_result(self, path):
        item = QtWidgets.QListWidgetItem(path)
        self.results.addItem(item)
        item.setSelected(True)

    def _import_selected(self):
        paths = [
            Path(item.text())
            for item in self.results.selectedItems()
            if Path(item.text()).suffix.lower() in {".webp", ".apng", ".gif"}
        ]
        if not paths:
            self.status.setText("請選取已輸出的 WebP／APNG／GIF 動畫；PNG 保留為單張圖片。")
            return
        key = self.target.currentData()
        if key is None:
            from .state.add_dialog import AddStateDialog

            dialog = AddStateDialog(self.service, self)
            dialog.selected_gif_paths = paths
            dialog.gif_label.setText(f"已選取 {len(paths)} 個成品")
            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                key = dialog.key_edit.text().strip()
                state = self.service.get_state(key)
                if state:
                    self.target.addItem(state.label or key, key)
                    self.target.setCurrentIndex(self.target.count() - 1)
            return
        failed = []
        for path in paths:
            try:
                if not self.service.add_gif(key, path):
                    failed.append(path.name)
            except (OSError, ValueError):
                failed.append(path.name)
        if failed:
            self.status.setText("部分匯入失敗：" + ", ".join(failed))
        else:
            self.status.setText(f"已新增 {len(paths)} 個動畫至姿勢 {key}，可從 States 選單切換。")
