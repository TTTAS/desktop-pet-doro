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
        kind, QtCore.QPointF(local, 5), QtCore.QPointF(x, 105),
        button, buttons, QtCore.Qt.KeyboardModifier.NoModifier,
    )


def press(handler):
    handler.handle_press(event(QtCore.QEvent.Type.MouseButtonPress, 105, button=LEFT),
                         QtCore.QRect(100, 100, 200, 200))


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
    assert handler.handle_release(event(QtCore.QEvent.Type.MouseButtonRelease, 117,
                                        button=LEFT, buttons=NONE)) == (True, False)
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
    handler.handle_release(event(QtCore.QEvent.Type.MouseButtonRelease, 107,
                                 button=LEFT, buttons=NONE))
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
        _automation=Mock(), _action_dispatcher=Mock(), _movement=Mock(),
        _presence=Mock(), _sprite_controller=sprite,
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
            handler.handle_release(event(QtCore.QEvent.Type.MouseButtonRelease, 120,
                                         button=LEFT, buttons=NONE))
        elif ending == "reset":
            handler.reset()
        else:
            window = DoroWindow(state_service=Mock())
            qtbot.addWidget(window)
            window._mouse_handler = handler
            kind = QtCore.QEvent.Type.WindowDeactivate if ending == "deactivate" else QtCore.QEvent.Type.UngrabMouse
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
        companion_file=tmp_path / "missing.txt", chat_orchestrator=Mock(),
        movement_manager=Mock(), state_service=Mock(),
        idle_seconds_provider=lambda: 999, mark_activity=Mock(),
        interaction_busy=lambda: True,
    )
    try:
        idle._schedule_next = Mock()
        idle._on_timer()
        idle._schedule_next.assert_called_once()
        idle._mark_activity.assert_not_called()
    finally:
        idle._timer.stop()
