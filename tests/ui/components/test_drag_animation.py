from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtGui

from doro_app.app import DoroApp
from doro_app.ui.controllers.sprite_controller import SpriteController
from doro_app.ui.events.mouse_event_handler import MouseEventHandler
from doro_app.ui.viewmodels.doro_viewmodel import DoroViewModel
from doro_app.ui.window import DoroWindow
from doro_app.utils.paths import DRAG_DIR

LEFT = QtCore.Qt.MouseButton.LeftButton
NONE = QtCore.Qt.MouseButton.NoButton


def event(kind, x, *, local=5, button=NONE, buttons=LEFT):
    return QtGui.QMouseEvent(
        kind,
        QtCore.QPointF(local, 5),
        QtCore.QPointF(x, 105),
        button,
        buttons,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )


def press(handler):
    handler.handle_press(
        event(QtCore.QEvent.Type.MouseButtonPress, 105, button=LEFT),
        QtCore.QRect(100, 100, 200, 200),
    )


def test_slow_drag_uses_total_screen_distance_and_does_not_click(qapp):
    handler = MouseEventHandler(click_threshold=6)
    started, finished, clicks, moves = Mock(), Mock(), Mock(), []
    handler.drag_started.connect(started)
    handler.drag_finished.connect(finished)
    handler.click_detected.connect(clicks)
    handler.window_drag_requested.connect(moves.append)
    press(handler)
    for x in (107, 109, 111):
        handler.handle_move(event(QtCore.QEvent.Type.MouseMove, x))
    assert not moves  # Small click jitter must not move the window.
    for x in (113, 115, 117):
        handler.handle_move(event(QtCore.QEvent.Type.MouseMove, x))
    assert handler.is_dragging
    started.assert_called_once()
    assert moves[-1] == QtCore.QPoint(112, 100)
    assert handler.handle_release(
        event(QtCore.QEvent.Type.MouseButtonRelease, 117, button=LEFT, buttons=NONE)
    ) == (True, False)
    finished.assert_called_once()
    clicks.assert_not_called()
    assert not handler.is_dragging


def test_click_does_not_play_drag_and_reset_is_idempotent(qapp):
    handler = MouseEventHandler(click_threshold=6)
    started, finished, clicks = Mock(), Mock(), Mock()
    handler.drag_started.connect(started)
    handler.drag_finished.connect(finished)
    handler.click_detected.connect(clicks)
    press(handler)
    handler.handle_release(
        event(QtCore.QEvent.Type.MouseButtonRelease, 107, button=LEFT, buttons=NONE)
    )
    started.assert_not_called()
    finished.assert_not_called()
    clicks.assert_called_once()
    press(handler)
    handler.handle_move(event(QtCore.QEvent.Type.MouseMove, 120))
    handler.reset()
    handler.reset()
    finished.assert_called_once()


@pytest.mark.parametrize("ending", ["release", "reset", "deactivate", "ungrab"])
def test_real_drag_movie_plays_and_restores_latest_sprite(qtbot, ending):
    sprite = SpriteController(DoroViewModel())
    handler = MouseEventHandler()
    assets = sorted(DRAG_DIR.glob("*.webp"))
    app = SimpleNamespace(
        _action_service=Mock(list_drag_gif_paths=Mock(return_value=list(assets))),
        _automation=Mock(),
        _action_dispatcher=Mock(),
        _movement=Mock(),
        _presence=Mock(),
        _sprite_controller=sprite,
    )
    handler.drag_started.connect(lambda: DoroApp._on_doro_dragged(app))
    handler.drag_finished.connect(sprite.end_drag_animation)
    window = None
    try:
        assert sprite.load_sprite(assets[0])
        normal_size = sprite._view_model.sprite_size
        press(handler)
        handler.handle_move(event(QtCore.QEvent.Type.MouseMove, 120))
        dragged = sprite.renderer.movie
        assert dragged is sprite._drag_movie
        assert dragged.state() == QtGui.QMovie.MovieState.Running
        first_frame = dragged.currentFrameNumber()
        qtbot.waitUntil(lambda: dragged.currentFrameNumber() > first_frame, timeout=2000)
        app._action_dispatcher.cancel_current.assert_called_once_with("drag")
        app._movement.cancel_active_movement.assert_called_once()
        app._presence.interrupt.assert_called_once()
        # State/transition changes during dragging cannot replace the overlay.
        assert sprite.load_sprite(assets[1])
        latest = sprite._current_movie
        sprite.set_movie_directly(latest, normal_size)
        assert sprite.renderer.movie is dragged
        assert sprite._view_model.sprite_size == normal_size
        count = sprite.gif_player.count()
        if ending == "release":
            handler.handle_release(
                event(QtCore.QEvent.Type.MouseButtonRelease, 120, button=LEFT, buttons=NONE)
            )
        elif ending == "reset":
            handler.reset()
        else:
            window = DoroWindow(state_service=Mock())
            qtbot.addWidget(window)
            window._mouse_handler = handler
            kind = (
                QtCore.QEvent.Type.WindowDeactivate
                if ending == "deactivate"
                else QtCore.QEvent.Type.UngrabMouse
            )
            QtCore.QCoreApplication.sendEvent(window, QtCore.QEvent(kind))
        assert sprite.renderer.movie is latest
        assert sprite._drag_movie is None
        assert sprite.gif_player.count() == count - 1
        assert not handler.is_dragging
    finally:
        sprite.dispose_all()
        sprite.gif_player.clear()


def test_missing_drag_asset_preserves_normal_sprite(qapp, tmp_path):
    sprite = SpriteController(DoroViewModel())
    try:
        assert sprite.load_sprite(next(DRAG_DIR.glob("*.webp")))
        normal = sprite.renderer.movie
        assert not sprite.start_drag_animation(tmp_path / "missing.webp")
        assert sprite.renderer.movie is normal
        sprite.end_drag_animation()
        assert sprite.renderer.movie is normal
    finally:
        sprite.dispose_all()
        sprite.gif_player.clear()


def test_idle_defers_while_user_is_dragging(qapp, tmp_path):
    from doro_app.core.idle_behavior_manager import IdleBehaviorManager

    idle = IdleBehaviorManager(
        companion_file=tmp_path / "missing.txt",
        chat_orchestrator=Mock(),
        movement_manager=Mock(),
        state_service=Mock(),
        idle_seconds_provider=lambda: 999,
        mark_activity=Mock(),
        interaction_busy=lambda: True,
    )
    try:
        idle._schedule_next = Mock()
        idle._on_timer()
        idle._schedule_next.assert_called_once()
        idle._mark_activity.assert_not_called()
    finally:
        idle._timer.stop()


@pytest.fixture
def drag_service(real_state_service, temp_gif_storage, tmp_path):
    from doro_app.core.action.repository import ActionRepository
    from doro_app.core.action.service import ActionService
    from doro_app.core.state import GifRepository

    service = ActionService(
        ActionRepository(tmp_path / "actions.json"),
        real_state_service,
        GifRepository(temp_gif_storage),
        drag_gif_repo=GifRepository(tmp_path / "res"),
    )
    service.bootstrap()
    return service, real_state_service, tmp_path / "res" / "drag"


def test_drag_pool_adds_and_removes_files_in_drag_folder(drag_service):
    service, _, drag_dir = drag_service
    assert service.list_drag_gif_paths() == []
    source = next(DRAG_DIR.glob("*.webp"))
    assert service.add_drag_gif(source)
    assert service.add_drag_gif(source)
    names = [p.name for p in service.list_drag_gif_paths()]
    assert names == ["drag_1.webp", "drag_2.webp"]
    assert all(p.parent == drag_dir for p in service.list_drag_gif_paths())
    assert service.remove_drag_gif("drag_1.webp")
    assert [p.name for p in service.list_drag_gif_paths()] == ["drag_2.webp"]
    assert not service.add_drag_gif(drag_dir / "missing.webp")


def test_drag_uses_menu_pool_and_skips_when_empty(qapp, drag_service):
    service, _, _ = drag_service
    sprite = Mock()
    app = SimpleNamespace(
        _action_service=service,
        _automation=None,
        _action_dispatcher=None,
        _movement=Mock(),
        _presence=None,
        _sprite_controller=sprite,
    )
    DoroApp._on_doro_dragged(app)
    sprite.start_drag_animation.assert_not_called()
    service.add_drag_gif(next(DRAG_DIR.glob("*.webp")))
    service.add_drag_gif(next(DRAG_DIR.glob("*.webp")))
    sprite.start_drag_animation.side_effect = [False, True]
    DoroApp._on_doro_dragged(app)
    tried = [c.args[0] for c in sprite.start_drag_animation.call_args_list]
    assert sorted(tried) == service.list_drag_gif_paths()


def test_drag_card_and_editor_manage_the_pool(qtbot, drag_service, monkeypatch):
    from PySide6 import QtWidgets

    from doro_app.core.action.repository import PET_DRAG_ACTION_KEY
    from doro_app.ui.dialogs.move_state.edit_dialog import EditMoveStateDialog
    from doro_app.ui.dialogs.move_state.manager_dialog import MoveStateManagerDialog
    from doro_app.ui.dialogs.state import gif_gallery_dialog

    service, state, _ = drag_service
    source = next(DRAG_DIR.glob("*.webp"))

    class FakeGallery:
        def __init__(self, *_args, **_kwargs):
            self.added_paths = [source]
            self.removed_filenames = []

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def cleanup(self):
            pass

    monkeypatch.setattr(gif_gallery_dialog, "GifGalleryDialog", FakeGallery)

    manager = MoveStateManagerDialog(state, action_service=service)
    qtbot.addWidget(manager)
    card = next(c for c in manager._cards if c._key == PET_DRAG_ACTION_KEY)
    assert card._manage_gifs and not card._gif_paths
    card.manage_gifs_clicked.emit(PET_DRAG_ACTION_KEY)
    assert len(service.list_drag_gif_paths()) == 1
    card = next(c for c in manager._cards if c._key == PET_DRAG_ACTION_KEY)
    assert len(card._gif_paths) == 1

    editor = EditMoveStateDialog(
        state, None, action_service=service, edit_action_key=PET_DRAG_ACTION_KEY
    )
    qtbot.addWidget(editor)
    assert not editor.manage_gifs_btn.isHidden()
    assert editor.select_gif_btn.isHidden()
    assert editor.gif_status_label.text() == "1 GIF(s)"
    editor._on_manage_transition_gifs()
    assert len(service.list_drag_gif_paths()) == 2
    assert editor.gif_status_label.text() == "2 GIF(s)"
    editor._save_action()
    assert editor.result() == QtWidgets.QDialog.DialogCode.Accepted
