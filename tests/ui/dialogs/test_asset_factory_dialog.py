"""Exercise the real Qt worker boundary and media import without an AI download."""

from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

pytest.importorskip("cv2")
pytest.importorskip("PIL")
from PIL import Image
from PySide6 import QtCore, QtWidgets

from doro_app.core.gif_factory.pipeline import ProcessingCancelled
from doro_app.ui.dialogs import asset_factory_dialog as module


@pytest.fixture
def dialog(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(module, "load_config", dict)
    monkeypatch.setattr(module, "save_config", lambda config: None)
    service = Mock()
    service.visible_state_keys.return_value = ["idle"]
    service.get_state.return_value = Mock(label="Idle")
    service.add_gif.return_value = True
    widget = module.AssetFactoryDialog(service)
    qtbot.addWidget(widget)
    widget.mode.setCurrentIndex(1)
    widget.output_dir.setText(str(tmp_path))
    yield widget
    widget.shutdown()


def test_load_preview_export_and_import(qtbot, dialog):
    fixture = Path(__file__).parents[2] / "gif_factory/fixtures/ComfyUI_00012_.mp4"
    dialog._paths = [fixture]
    dialog._load_video(0)
    qtbot.waitUntil(lambda: dialog._job is None and bool(dialog._frames), timeout=15000)
    qtbot.waitUntil(
        lambda: dialog._job is None and "預覽完成" in dialog.status.text(), timeout=15000
    )
    assert not dialog.preview.pixmap().isNull()
    dialog._export_frame()
    qtbot.waitUntil(lambda: dialog._job is None, timeout=15000)
    png = Path(dialog.results.item(0).text())
    assert Image.open(png).mode == "RGBA"
    dialog.size.setValue(48)
    dialog._export_animation()
    qtbot.waitUntil(lambda: dialog._job is None, timeout=30000)
    webp = Path(dialog.results.item(1).text())
    with Image.open(webp) as image:
        assert image.n_frames > 1
        assert max(image.size) == 48
    dialog.target.setCurrentIndex(1)
    dialog._import_selected()
    dialog.service.add_gif.assert_called_once_with("idle", webp)


def test_gif_converts_to_uniform_canvas_gif_and_imports(qtbot, dialog, tmp_path):
    source = tmp_path / "web.gif"
    frames = [Image.new("RGBA", (30, 12), (0, 0, 0, 0)) for _ in range(3)]
    for i, frame in enumerate(frames):
        frame.paste((255, 0, 0, 255), (i * 5, 2, i * 5 + 5, 8))
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=80, loop=0)
    dialog.mode.setCurrentIndex(dialog.mode.findData("none"))
    dialog.fmt.setCurrentText("gif")
    dialog.size_mode.setCurrentIndex(dialog.size_mode.findData("canvas"))
    dialog.size.setValue(64)
    dialog._paths = [source]
    dialog._load_video(0)
    qtbot.waitUntil(lambda: dialog._job is None and bool(dialog._frames), timeout=15000)
    qtbot.waitUntil(lambda: dialog._job is None and "預覽完成" in dialog.status.text())
    dialog._export_animation()
    qtbot.waitUntil(lambda: dialog._job is None and dialog.results.count() == 1, timeout=15000)
    gif = Path(dialog.results.item(0).text())
    assert gif.suffix == ".gif" and gif != source
    with Image.open(gif) as image:
        assert image.size == (64, 64)
        assert image.n_frames == 3
    dialog.target.setCurrentIndex(1)
    dialog._import_selected()
    dialog.service.add_gif.assert_called_once_with("idle", gif)


def test_original_size_mode_disables_size_box(dialog):
    dialog.size_mode.setCurrentIndex(dialog.size_mode.findData("original"))
    assert not dialog.size.isEnabled()
    assert dialog._export_settings()[1:] == (None, False)


def test_failed_load_clears_previous_source(qtbot, dialog, tmp_path):
    dialog._frames = [Image.new("RGB", (20, 20))]
    dialog._paths = [tmp_path / "missing.mp4"]
    dialog._load_video(0)
    qtbot.waitUntil(lambda: dialog._job is None)
    assert not dialog._frames
    assert not dialog.animate.isEnabled()
    assert "找不到" in dialog.status.text()


def test_close_waits_for_cancelled_worker(qtbot, dialog):
    started = Event()

    def work(job):
        started.set()
        job.cancel.wait(5)
        raise ProcessingCancelled("已取消")

    dialog.show()
    dialog._start_job(work, lambda result: pytest.fail("cancelled work cannot succeed"))
    qtbot.waitUntil(started.is_set)
    dialog.reject()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert not dialog.isVisible()


def test_worker_completion_runs_on_gui_thread(qtbot, dialog):
    observed = []
    dialog._start_job(
        lambda job: QtCore.QThread.currentThread(),
        lambda worker_thread: observed.append((worker_thread, QtCore.QThread.currentThread())),
    )
    qtbot.waitUntil(lambda: bool(observed))
    worker, completion = observed[0]
    assert worker != completion
    assert completion == QtWidgets.QApplication.instance().thread()


def test_import_failures_are_visible(dialog):
    dialog._add_result("result.webp")
    dialog.target.setCurrentIndex(1)
    dialog.service.add_gif.return_value = False
    dialog._import_selected()
    assert "失敗" in dialog.status.text()


def test_missing_optional_dependencies_show_install_help(qtbot, monkeypatch):
    import builtins

    from doro_app.ui.controllers.dialog_manager import DialogManager

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if "asset_factory_dialog" in name:
            raise ImportError("No module named cv2")
        return original(name, *args, **kwargs)

    message = Mock()
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", message)
    DialogManager(None, Mock()).show_asset_factory()
    assert ".[factory]" in message.call_args.args[2]
