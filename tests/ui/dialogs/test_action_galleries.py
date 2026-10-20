"""All action cards expose the same gallery, including real persisted playback pools."""

import pytest
from PIL import Image
from PySide6 import QtWidgets

from doro_app.core.action.repository import ActionRepository
from doro_app.core.action.service import ActionService
from doro_app.core.state import GifRepository, Transition
from doro_app.ui.dialogs.move_state.edit_dialog import EditMoveStateDialog
from doro_app.ui.dialogs.move_state.manager_dialog import MoveStateManagerDialog
from doro_app.ui.dialogs.state.gif_gallery_dialog import GifGalleryDialog


@pytest.fixture
def gallery_services(real_state_service, temp_gif_storage, tmp_path):
    state = real_state_service
    state.add_state("pose", "Pose")
    state.add_state("rest", "Rest")
    state.add_move_state("walk", "pose", direction="left", speed="fast")
    state.add_transition(Transition(key="rise", from_state="rest", to_state="pose"))
    repo = ActionRepository(tmp_path / "actions.json")
    action = ActionService(
        repo, state, GifRepository(temp_gif_storage), drag_gif_repo=GifRepository(tmp_path / "res")
    )
    action.bootstrap()
    sources = []
    for name, color in (("first", "red"), ("second", "blue"), ("third", "green")):
        path = tmp_path / f"{name}.gif"
        Image.new("RGB", (12, 12), color).save(path)
        sources.append(path)
    return state, action, repo, sources


@pytest.mark.parametrize("key", ["click", "pet_click"])
def test_legacy_binding_becomes_persistent_random_pool(gallery_services, key, monkeypatch):
    state, action, repo, sources = gallery_services
    bind = action.bind_click_gif if key == "click" else action.bind_pet_click_gif
    assert bind(sources[0])
    action.bootstrap()
    assert action.add_action_gif(key, sources[1])
    assert action.add_action_gif(key, sources[2])
    pool = action.list_action_gif_paths(key)
    assert len(pool) == 3
    assert {p.read_bytes() for p in pool} == {p.read_bytes() for p in sources}
    for index in range(3):
        monkeypatch.setattr("random.choice", lambda choices, i=index: choices[i])
        assert action.resolve_action_gif_path(key) == pool[index]
        if key == "click":
            assert state.get_gif_path("click_action") == pool[index]
            assert state.get_gif_path("click_failed").exists()
    assert action.remove_action_gif(key, pool[0].name)
    assert not pool[0].exists()
    repo.load()
    action.bootstrap()
    assert action.list_action_gif_paths(key) == pool[1:]
    for path in pool[1:]:
        assert action.remove_action_gif(key, path.name)
    repo.load()
    assert action.list_action_gif_paths(key) == []
    assert repo.get(key).gif_id is None
    if key == "pet_click":
        assert action.resolve_action_gif_path(key) is None


@pytest.mark.parametrize("key", ["click", "pet_click", "pet_drag", "walk", "rise"])
def test_card_gallery_add_delete_cancel_and_reopen(qtbot, gallery_services, key, monkeypatch):
    state, action, _, sources = gallery_services
    manager = MoveStateManagerDialog(state, action_service=action)
    qtbot.addWidget(manager)

    def card():
        return next(c for c in manager._cards if c._key == key)

    def edit_gallery(dialog):
        # Exercise the real multi-select path and real Windows QMovie handles.
        dialog._on_add()
        assert len(dialog.added_paths) == 3
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileNames", lambda *a, **kw: ([str(p) for p in sources], "")
    )
    monkeypatch.setattr(GifGalleryDialog, "exec", edit_gallery)
    button = next(b for b in card().findChildren(QtWidgets.QPushButton) if b.text() == "GIFs")
    button.click()
    assert len(card()._gif_paths) == 3
    first = card()._gif_paths[0]
    card()._navigate(1)
    assert card()._counter.text() == "2/3"

    def cancel_gallery(dialog):
        dialog._on_remove_gif(first.name)
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(GifGalleryDialog, "exec", cancel_gallery)
    card().manage_gifs_clicked.emit(key)
    assert first.exists()
    assert len(card()._gif_paths) == 3

    def delete_gallery(dialog):
        dialog._on_remove_gif(first.name)
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(GifGalleryDialog, "exec", delete_gallery)
    card().manage_gifs_clicked.emit(key)
    assert not first.exists()
    assert len(card()._gif_paths) == 2
    manager.close()
    reopened = MoveStateManagerDialog(state, action_service=action)
    qtbot.addWidget(reopened)
    assert len(next(c for c in reopened._cards if c._key == key)._gif_paths) == 2
    reopened.close()


def test_uniform_controls_and_settings_preserve_transition(qtbot, gallery_services, monkeypatch):
    state, action, _, _ = gallery_services
    manager = MoveStateManagerDialog(state, action_service=action)
    qtbot.addWidget(manager)
    for card in manager._cards:
        buttons = {
            b.text(): b
            for b in card.findChildren(QtWidgets.QPushButton)
            if b.text() in ("GIFs", "設定", "刪除")
        }
        assert list(buttons) == ["GIFs", "設定", "刪除"]
        assert buttons["GIFs"].isEnabled()
        assert buttons["設定"].isEnabled() == (card._action_type != "action")
        assert buttons["刪除"].isEnabled() == (card._action_type != "action")

    def edit_transition(dialog):
        assert dialog.action_type == "transition"
        assert dialog.key_edit.text() == "rise"
        assert dialog.from_state_combo.currentText() == "rest"
        assert dialog.to_state_combo.currentText() == "pose"
        assert dialog.manage_gifs_btn.parentWidget().isHidden()
        dialog._on_accept()
        return dialog.result()

    monkeypatch.setattr(EditMoveStateDialog, "exec", edit_transition)
    manager._on_edit("transition", "rise")
    assert state.get_transition("rise").from_state == "rest"
    assert state.get_move_state("rise") is None
    manager.close()


@pytest.mark.parametrize("key", ["click", "pet_click", "pet_drag"])
def test_add_editor_uses_multi_gallery(qtbot, gallery_services, key, monkeypatch):
    state, action, _, sources = gallery_services
    editor = EditMoveStateDialog(state, None, action_service=action)
    qtbot.addWidget(editor)
    editor.type_combo.setCurrentText("Action")
    editor.named_action_combo.setCurrentIndex(editor.named_action_combo.findData(key))
    assert not editor.manage_gifs_btn.isHidden()
    assert editor.select_gif_btn.isHidden()

    def add(dialog):
        dialog._added = sources[:2]
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(GifGalleryDialog, "exec", add)
    editor.manage_gifs_btn.click()
    assert editor.gif_status_label.text() == "2 GIF(s)"
    editor.reject()


def test_movement_preserves_legacy_asset_and_replacement_does_not_revive_it(gallery_services):
    state, _, _, sources = gallery_services
    # Old movement art can live outside the normal state subfolder.
    legacy_id = state.store_gif(sources[0], "old_movement")
    assert state.update_state("pose", gif_id=legacy_id)
    assert state.add_gif("pose", sources[1])
    pool = state.list_gif_paths("pose")
    assert len(pool) == 2
    assert {p.read_bytes() for p in pool} == {p.read_bytes() for p in sources[:2]}
    for path in pool:
        assert state.remove_gif("pose", path.name)
    assert state.add_gif("pose", sources[2])
    assert [p.read_bytes() for p in state.list_gif_paths("pose")] == [sources[2].read_bytes()]


def test_single_movement_can_be_replaced_from_gallery(gallery_services):
    state, _, _, sources = gallery_services
    assert state.set_gif("pose", sources[0])
    first = state.get_gif_path("pose")
    assert state.remove_gif("pose", first.name)
    assert not first.exists()
    assert state.add_gif("pose", sources[1])
    assert len(state.list_gif_paths("pose")) == 1


@pytest.mark.parametrize("key", ["click", "pet_click"])
def test_legacy_replace_and_clear_apis_also_update_pools(gallery_services, key):
    _, action, _, sources = gallery_services
    assert action.add_action_gif(key, sources[0])
    assert action.add_action_gif(key, sources[1])
    bind = action.bind_click_gif if key == "click" else action.bind_pet_click_gif
    clear = action.unbind_click_gif if key == "click" else action.unbind_pet_click_gif
    assert bind(sources[2])
    assert [p.read_bytes() for p in action.list_action_gif_paths(key)] == [sources[2].read_bytes()]
    assert clear()
    assert action.list_action_gif_paths(key) == []


def test_empty_click_pool_uses_stand_without_exposing_it_in_gallery(gallery_services):
    state, action, _, sources = gallery_services
    state.add_state("stand", "Stand")
    state.set_gif("stand", sources[0])
    action.add_action_gif("click", sources[1])
    action.remove_action_gif("click", action.list_action_gif_paths("click")[0].name)
    assert action.list_action_gif_paths("click") == []
    assert action.resolve_action_gif_path("click") == state.get_gif_path("stand")
    assert state.get_gif_path("click_action") == state.get_gif_path("stand")


def test_transition_can_use_any_state(qtbot, gallery_services, monkeypatch):
    from doro_app.ui.dialogs.move_state.edit_dialog import ANY_STATE_LABEL

    state, action, _, _ = gallery_services
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    dialog = EditMoveStateDialog(state, None, action_service=action)
    qtbot.addWidget(dialog)
    dialog._on_action_type_changed("Transition")
    assert dialog.from_state_combo.itemText(0) == ANY_STATE_LABEL
    assert dialog.from_state_combo.currentData() != "*"  # 預設仍是具體狀態

    dialog.key_edit.setText("wake_any")
    dialog.from_state_combo.setCurrentIndex(dialog.from_state_combo.findData("*"))
    dialog.to_state_combo.setCurrentIndex(dialog.to_state_combo.findData("rest"))
    dialog._on_accept()

    assert warnings == []
    saved = state.get_transition("wake_any")
    assert (saved.from_state, saved.to_state) == ("*", "rest")
    assert state.find_transition("rest", "pose").key == "rise"  # 其他精確配對不受影響
    assert state.find_transition("pose", "rest").key == "wake_any"

    manager = MoveStateManagerDialog(state, action_service=action)
    qtbot.addWidget(manager)
    card = next(c for c in manager._cards if c._key == "wake_any")
    assert any(ANY_STATE_LABEL in label.text() for label in card.findChildren(QtWidgets.QLabel))

    def edit(dialog):
        assert dialog.from_state_combo.currentData() == "*"
        assert dialog.to_state_combo.currentData() == "rest"
        return 0

    monkeypatch.setattr(EditMoveStateDialog, "exec", edit)
    manager._on_edit("transition", "wake_any")
    manager.close()


def test_any_to_any_is_allowed_but_same_state_is_not(qtbot, gallery_services, monkeypatch):
    state, action, _, _ = gallery_services
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    dialog = EditMoveStateDialog(state, None, action_service=action)
    qtbot.addWidget(dialog)
    dialog._on_action_type_changed("Transition")

    dialog.key_edit.setText("same")
    dialog.from_state_combo.setCurrentIndex(dialog.from_state_combo.findData("rest"))
    dialog.to_state_combo.setCurrentIndex(dialog.to_state_combo.findData("rest"))
    dialog._on_accept()
    assert state.get_transition("same") is None
    assert warnings == ["From and To states must be different."]

    dialog.key_edit.setText("universal")
    dialog.from_state_combo.setCurrentIndex(0)
    dialog.to_state_combo.setCurrentIndex(0)
    dialog._on_accept()
    assert state.get_transition("universal").from_state == "*"
