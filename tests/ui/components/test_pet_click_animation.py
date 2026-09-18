import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtWidgets

from doro_app.app import DoroApp
from doro_app.core.action.repository import PET_CLICK_ACTION_KEY, ActionRepository
from doro_app.core.action.service import ActionService
from doro_app.core.state import GifRepository
from doro_app.ui.controllers.sprite_controller import SpriteController
from doro_app.ui.dialogs.move_state.edit_dialog import EditMoveStateDialog
from doro_app.ui.dialogs.move_state.manager_dialog import MoveStateManagerDialog
from doro_app.ui.events.mouse_event_handler import MouseEventHandler
from doro_app.ui.viewmodels.doro_viewmodel import DoroViewModel
from tests.ui.components.test_drag_animation import LEFT, NONE, event, press


@pytest.fixture
def assets(tmp_path):
    # Tiny GIF fixtures: two static poses and a three-frame looping gesture.
    encoded = {
        "normal": "R0lGODlhGAAYAIEAAAAA/wAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAAGAAYAEAIKQABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDPgwIADs=",
        "pet": "R0lGODlhGAAYAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAAGAAYAAAIKQABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDPgwIACH5BAEGAAEALAAAAAAYABgAgf//AAAAAAAAAAAAAAgpAAEIHEiwoMGDCBMqXMiwocOHECNKnEixosWLGDNq3Mixo8ePIEM+DAgAIfkEAQYAAQAsAAAAABgAGACBAIAAAAAAAAAAAAAACCkAAQgcSLCgwYMIEypcyLChw4cQI0qcSLGixYsYM2rcyLGjx48gQz4MCAA7",
        "new": "R0lGODlhGAAYAIEAAP///wAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAAGAAYAEAIKQABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDPgwIADs=",
    }
    paths = []
    for name, data in encoded.items():
        path = tmp_path / f"{name}.gif"
        path.write_bytes(base64.b64decode(data))
        paths.append(path)
    return paths


@pytest.fixture
def sprite(qapp):
    controller = SpriteController(DoroViewModel())
    yield controller
    controller.dispose_all()
    controller.gif_player.clear()


@pytest.mark.parametrize("finite", [False, True])
def test_one_loop_reveals_latest_sprite(qtbot, sprite, assets, finite):
    normal, pet, new = assets
    if finite:
        pet.write_bytes(pet.read_bytes().replace(b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00", b""))
    assert sprite.load_sprite(normal)
    assert sprite.start_pet_click_animation(pet)
    gesture = sprite.renderer.movie
    qtbot.waitUntil(lambda: gesture.currentFrameNumber() > 0)
    assert sprite.load_sprite(new)
    latest = sprite._current_movie
    assert sprite.renderer.movie is gesture
    count = sprite.gif_player.count()
    qtbot.waitUntil(lambda: sprite._pet_click_movie is None, timeout=2000)
    assert sprite.renderer.movie is latest
    assert sprite.gif_player.count() == count - 1


def test_repeated_click_restarts_and_drag_takes_over(qtbot, sprite, assets):
    normal, pet, _ = assets
    sprite.load_sprite(normal)
    sprite.start_pet_click_animation(pet)
    count = sprite.gif_player.count()
    sprite.start_pet_click_animation(pet)
    assert sprite.gif_player.count() == count
    assert sprite.start_drag_animation(pet)
    dragged = sprite.renderer.movie
    assert sprite._pet_click_movie is None
    assert not sprite.start_pet_click_animation(pet)
    qtbot.wait(450)
    assert sprite.renderer.movie is dragged
    sprite.end_drag_animation()
    assert sprite.renderer.movie is sprite._current_movie


def test_static_gesture_and_missing_asset_do_not_get_stuck(qtbot, sprite, assets, tmp_path):
    sprite.load_sprite(assets[0])
    normal = sprite.renderer.movie
    assert not sprite.start_pet_click_animation(tmp_path / "missing.gif")
    assert sprite.renderer.movie is normal
    assert sprite.start_pet_click_animation(assets[2])
    qtbot.waitUntil(lambda: sprite._pet_click_movie is None, timeout=2000)
    assert sprite.renderer.movie is normal


def test_mouse_click_triggers_gesture_even_when_chat_busy_but_drag_does_not(qapp, sprite, assets):
    handler = MouseEventHandler()
    action_service = Mock()
    action_service.resolve_action_gif_path.return_value = assets[1]
    app = SimpleNamespace(
        window=Mock(),
        _action_service=action_service,
        _sprite_controller=sprite,
        _click_action_controller=Mock(),
    )
    app._click_action_controller.trigger_random_action.return_value = False
    handler.click_detected.connect(lambda: DoroApp._on_doro_clicked(app))
    sprite.load_sprite(assets[0])
    press(handler)
    handler.handle_release(
        event(QtCore.QEvent.Type.MouseButtonRelease, 105, button=LEFT, buttons=NONE)
    )
    assert sprite._pet_click_movie is not None
    action_service.resolve_action_gif_path.assert_called_once_with(PET_CLICK_ACTION_KEY)
    sprite.end_pet_click_animation()
    action_service.resolve_action_gif_path.reset_mock()
    press(handler)
    handler.handle_move(event(QtCore.QEvent.Type.MouseMove, 120))
    handler.handle_release(
        event(QtCore.QEvent.Type.MouseButtonRelease, 120, button=LEFT, buttons=NONE)
    )
    action_service.resolve_action_gif_path.assert_not_called()
    action_service.resolve_action_gif_path.return_value = None
    normal = sprite.renderer.movie
    DoroApp._on_doro_clicked(app)
    assert sprite.renderer.movie is normal


@pytest.fixture
def action_service(real_state_service, temp_gif_storage, tmp_path):
    repo = ActionRepository(tmp_path / "actions.json")
    service = ActionService(repo, real_state_service, GifRepository(temp_gif_storage))
    service.bootstrap()
    return service, repo, real_state_service


def test_pet_binding_persists_independently_and_can_be_cleared(action_service, assets):
    service, repo, _ = action_service
    assert repo.get(PET_CLICK_ACTION_KEY).is_builtin
    assert service.resolve_action_gif_path(PET_CLICK_ACTION_KEY) is None
    assert service.bind_click_gif(assets[0])
    desktop = service.resolve_action_gif_path("click")
    assert service.resolve_action_gif_path(PET_CLICK_ACTION_KEY) is None
    assert service.bind_pet_click_gif(assets[1])
    repo.load()
    assert (
        service.resolve_action_gif_path(PET_CLICK_ACTION_KEY).read_bytes() == assets[1].read_bytes()
    )
    assert service.resolve_action_gif_path("click") == desktop
    assert desktop.read_bytes() == assets[0].read_bytes()
    assert service.unbind_pet_click_gif()
    repo.load()
    assert service.resolve_action_gif_path(PET_CLICK_ACTION_KEY) is None
    assert service.resolve_action_gif_path("click") == desktop


def test_action_card_exists_without_gif_and_editor_saves_correct_binding(
    qtbot, action_service, assets
):
    service, repo, state = action_service
    manager = MoveStateManagerDialog(state, action_service=service)
    qtbot.addWidget(manager)
    assert {card._key for card in manager._cards if card._action_type == "action"} == {
        "click",
        "pet_click",
    }
    editor = EditMoveStateDialog(
        state, None, action_service=service, edit_action_key=PET_CLICK_ACTION_KEY
    )
    qtbot.addWidget(editor)
    assert editor.key_edit.text() == PET_CLICK_ACTION_KEY
    assert "尚未設定" in editor.gif_status_label.text()
    editor._save_action()
    assert editor.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert repo.get(PET_CLICK_ACTION_KEY).gif_id is None
    editor.selected_gif_path = assets[1]
    editor._save_action()
    assert repo.get(PET_CLICK_ACTION_KEY).gif_id
    assert repo.get("click").gif_id is None
    editor._on_clear_pet_gif()
    editor._save_action()
    assert repo.get(PET_CLICK_ACTION_KEY).gif_id is None


def test_add_action_can_select_pet_click(qtbot, action_service):
    service, _, state = action_service
    editor = EditMoveStateDialog(state, None, action_service=service)
    qtbot.addWidget(editor)
    editor.type_combo.setCurrentText("Action")
    editor.named_action_combo.setCurrentIndex(
        editor.named_action_combo.findData(PET_CLICK_ACTION_KEY)
    )
    assert editor.key_edit.text() == PET_CLICK_ACTION_KEY
    assert "點擊 Doro 本體" in editor.info_label.text()
