from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from doro_app.ui.dialogs.companion_dialog import CompanionDialog
from doro_app.ui.rendering.pet_expression import PetExpression
from doro_app.utils.config_manager import ConfigManager
from doro_app.utils.paths import STATE_DIR
from tests.ui.test_grounding import place

pytest_plugins = ["tests.ui.test_grounding"]


@pytest.fixture
def preferences(pet, real_state_service, qtbot):
    window, _, sprite = pet
    real_state_service.initialize(STATE_DIR / "idle.gif")
    sprite.load_sprite(STATE_DIR / "idle.gif")
    place(window, 600, 500)
    dialog = CompanionDialog(window._config_manager, real_state_service, window)
    qtbot.addWidget(dialog)
    yield dialog, window, real_state_service
    dialog.cleanup()
    sprite.dispose_all()
    sprite.gif_player.clear()


def test_cancel_keeps_settings_and_does_not_import_gif(preferences, monkeypatch):
    dialog, window, states = preferences
    before = list(states.visible_state_keys())
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *_: (str(STATE_DIR / "idle.gif"), "")
    )
    dialog.interval.setValue(120)
    dialog.effects.setChecked(False)
    dialog._choose_gif()
    assert dialog._pending_gif is not None
    dialog.reject()
    assert window._config_manager.ui.companion_interval_seconds == 9
    assert window._config_manager.ui.companion_effects
    assert states.visible_state_keys() == before
    assert dialog._movie is None


def test_import_on_accept_creates_rest_state_and_persists_preferences(preferences, monkeypatch):
    dialog, window, states = preferences
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *_: (str(STATE_DIR / "idle.gif"), "")
    )
    dialog._choose_gif()
    dialog.interval.setValue(37)
    dialog.effects.setChecked(False)
    dialog.accept()
    restored = ConfigManager(window._config_manager._settings.fileName())
    assert restored.ui.companion_interval_seconds == 37
    assert not restored.ui.companion_effects
    assert restored.ui.companion_rest_state.startswith("rest_")
    assert states.get_gif_path(restored.ui.companion_rest_state).is_file()


def test_import_failure_removes_partial_state_without_saving_settings(preferences, monkeypatch):
    dialog, window, states = preferences
    before = states.visible_state_keys()
    dialog._pending_gif = STATE_DIR / "idle.gif"
    monkeypatch.setattr(states, "set_gif", lambda *_: False)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", Mock())
    dialog.accept()
    assert states.visible_state_keys() == before
    assert window._config_manager.ui.companion_rest_state == "idle"
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted


def test_calibration_keeps_world_foot_and_survives_reload(preferences, qtbot):
    dialog, window, states = preferences
    foot = window.foot_position()
    dialog.anchor.setValue(82)
    key = window.current_gif_key()
    dialog.accept()
    assert window.foot_position() == foot
    assert (
        ConfigManager(window._config_manager._settings.fileName()).ui.sprite_foot_overrides[key]
        == 0.82
    )
    other = CompanionDialog(window._config_manager, states, window)
    qtbot.addWidget(other)
    assert other.anchor.value() == 82
    other._reset_anchor()
    other.accept()
    assert key not in window._config_manager.ui.sprite_foot_overrides
    assert window.foot_position() == foot


def test_calibration_preview_line_can_be_clicked(preferences, qtbot):
    dialog, _, _ = preferences
    dialog.show()
    dialog.findChild(QtWidgets.QTabWidget).setCurrentIndex(1)
    rect = dialog.foot_preview.image_rect()
    qtbot.mouseClick(
        dialog.foot_preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(rect.center().x(), rect.top() + round(0.75 * (rect.height() - 1))),
    )
    assert dialog.anchor.value() == pytest.approx(75, abs=0.8)
    dialog.reject()


@pytest.mark.parametrize("gesture", ["pet_click", "drag"])
def test_calibration_survives_gesture_and_bubble_relayout(
    preferences, pet, tmp_path, qtbot, gesture
):
    dialog, window, states = preferences
    _, bubble, sprite = pet
    dialog.anchor.setValue(82)
    dialog.accept()
    key = window.current_gif_key()
    foot = window.foot_position()
    contact = window.sprite_contact_rect().size()
    path = tmp_path / "gesture.gif"
    path.write_bytes((STATE_DIR / "idle.gif").read_bytes())
    assert getattr(sprite, f"start_{gesture}_animation")(path)
    assert window.current_gif_key() == key
    assert window.foot_position() == foot
    preview = CompanionDialog(window._config_manager, states, window)
    qtbot.addWidget(preview)
    assert preview._gif_key == key
    assert preview.anchor.value() == 82
    assert (
        preview.foot_preview.pixmap.cacheKey()
        == sprite.renderer.base_movie.currentPixmap().cacheKey()
    )
    preview.reject()
    for text in ["摸摸！", "正在拖曳時也保持校正。" * 5, ""]:
        bubble.set_text(text, auto_hide=False)
        assert window.foot_position() == foot
        assert window.sprite_contact_rect().size() == contact
    getattr(sprite, f"end_{gesture}_animation")()
    assert window.foot_position() == foot


@pytest.mark.parametrize("failure", ["unreadable", "create", "copy"])
def test_import_failures_explain_problem_and_allow_retry(
    preferences, monkeypatch, tmp_path, failure
):
    dialog, window, states = preferences
    before = states.visible_state_keys()
    warn = Mock()
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", warn)
    if failure == "unreadable":
        path = tmp_path / "broken.gif"
        path.write_text("not a GIF")
        monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
        dialog._choose_gif()
        assert dialog._pending_gif is None
    else:
        dialog._pending_gif = STATE_DIR / "idle.gif"
        with monkeypatch.context() as patch:
            patch.setattr(
                states, "add_state" if failure == "create" else "set_gif", lambda *_: False
            )
            dialog.accept()
        assert dialog._pending_gif == STATE_DIR / "idle.gif"
    warn.assert_called_once()
    assert states.visible_state_keys() == before
    assert window._config_manager.ui.companion_rest_state == "idle"
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
    dialog._pending_gif = STATE_DIR / "idle.gif"
    dialog.accept()
    assert states.get_gif_path(window._config_manager.ui.companion_rest_state).is_file()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted


def test_autonomous_pose_checklist_is_explicit_and_persisted(preferences, qtbot):
    dialog, window, states = preferences
    dialog.reject()
    states.add_state("angry", "生氣")
    states.add_state("play", "玩耍")
    other = CompanionDialog(window._config_manager, states, window)
    qtbot.addWidget(other)
    for i in range(other.pose_list.count()):
        item = other.pose_list.item(i)
        key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        assert (item.checkState() == QtCore.Qt.CheckState.Checked) == (key == "happy")
        item.setCheckState(
            QtCore.Qt.CheckState.Checked if key == "play" else QtCore.Qt.CheckState.Unchecked
        )
    other._pending_gif = STATE_DIR / "idle.gif"
    other.accept()
    config = ConfigManager(window._config_manager._settings.fileName())
    assert config.ui.companion_pose_keys == ["play"]
    assert config.ui.companion_rest_state not in config.ui.companion_pose_keys


def test_expression_is_bounded_and_anchor_stays_fixed():
    expression = PetExpression()
    assert expression.start("heart", 10)
    assert not expression.start("heart", 10.2)
    expression.advance(0.6)
    image = QtGui.QImage(240, 240, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    foot = QtCore.QPoint(120, 210)
    expression.transform(painter, foot)
    assert painter.transform().map(QtCore.QPointF(foot)) == QtCore.QPointF(foot)
    painter.end()
    expression.advance(2)
    assert not expression.kind


@pytest.mark.parametrize("x", [110, 600, 1090])
def test_expression_painting_keeps_foot_and_disabled_effects_clear(pet, x):
    window, _, _ = pet
    place(window, x, 799)
    foot = window.foot_position()
    window.play_expression("heart")
    window._pet_expression.advance(0.5)
    window.grab()
    assert window.foot_position() == foot
    window._config_manager.update_ui(companion_effects=False)
    window._tick()
    assert not window._pet_expression.kind
    window.play_expression("stretch")
    assert not window._pet_expression.kind


def test_interval_can_be_typed_directly(preferences, qtbot):
    dialog, _, _ = preferences
    editor = dialog.interval.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "23")
    dialog.interval.interpretText()
    assert dialog.interval.value() == 23
    dialog.accept()
    assert dialog._config.ui.companion_interval_seconds == 23


def test_heartbeat_tab_saves_settings_and_opens_checklist(
    pet, real_state_service, qtbot, tmp_path, monkeypatch
):
    window, _, sprite = pet
    real_state_service.initialize(STATE_DIR / "idle.gif")
    checklist = tmp_path / "heartbeat.md"
    opened = []
    monkeypatch.setattr(
        QtGui.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True
    )
    dialog = CompanionDialog(
        window._config_manager, real_state_service, window, checklist_path=checklist
    )
    qtbot.addWidget(dialog)
    try:
        assert not dialog.heartbeat_enabled.isChecked()
        assert dialog.heartbeat_interval.value() == 30
        dialog.checklist_button.click()
        assert checklist.is_file()
        assert opened == [str(checklist)]
        dialog.heartbeat_enabled.setChecked(True)
        dialog.heartbeat_interval.setValue(15)
        dialog.accept()
        restored = ConfigManager(window._config_manager._settings.fileName())
        assert restored.ui.heartbeat_enabled
        assert restored.ui.heartbeat_interval_minutes == 15
    finally:
        dialog.cleanup()
        sprite.dispose_all()
        sprite.gif_player.clear()


def test_checklist_button_disabled_without_path(preferences):
    dialog, _window, _states = preferences
    assert not dialog.checklist_button.isEnabled()
