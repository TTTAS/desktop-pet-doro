"""Foot-position regressions using actual Qt windows, not frame-only fakes."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore, QtGui

from doro_app.core.companion import CompanionController
from doro_app.core.movement.manager import MovementManager
from doro_app.core.movement.repository import MovementRepository
from doro_app.ui.components.bubble_controller import BubbleController
from doro_app.ui.components.speech_bubble_window import SpeechBubbleWindow
from doro_app.ui.controllers.sprite_controller import SpriteController
from doro_app.ui.events.mouse_event_handler import MouseEventHandler
from doro_app.ui.window import DoroWindow
from doro_app.utils.config_manager import ConfigManager


@pytest.fixture
def pet(qtbot, tmp_path):
    config = ConfigManager(tmp_path / "test.ini")
    window = DoroWindow(Mock(), config_manager=config)
    qtbot.addWidget(window)
    bubble = BubbleController(config)
    sprite = SpriteController(window.view_model)
    window.inject_controllers(
        state_controller=Mock(),
        sprite_controller=sprite,
        dialog_manager=Mock(),
        click_action_controller=Mock(),
        bubble_controller=bubble,
        mouse_handler=MouseEventHandler(),
    )
    window._timer.stop()
    area = QtCore.QRect(0, 0, 1200, 800)
    window._available_screen_geometry = lambda: area
    window.floor_geometry = lambda: area
    speech = SpeechBubbleWindow(
        window.view_model,
        bubble,
        body_on_screen=window.body_on_screen,
        work_area=window.floor_geometry,
        parent=window,
    )
    # Same wiring as DoroApp.
    bubble.text_changed.connect(lambda *_: speech.refresh())
    bubble.visibility_changed.connect(lambda *_: speech.refresh())
    window.sprite_geometry_changed.connect(speech.follow)
    sprite.sprite_renderer_changed.connect(window.on_sprite_renderer_changed)
    window.apply_window_preferred_size()
    window.show()
    yield window, bubble, sprite, speech
    bubble.clear_text()
    window.close()


def place(window, x, y):
    window.move_window_to(
        window.clamp_window_position(QtCore.QPoint(x, y) - window.sprite_foot_offset_logical())
    )


@pytest.mark.parametrize("x", [110, 600, 1090])
def test_talking_never_moves_or_resizes_doro_and_bubble_sits_above(pet, x):
    window, bubble, _, speech = pet
    place(window, x, 799)
    geometry = window.geometry()
    for text in ("我在這裡陪你。", "先忙你的事情，我在旁邊休息一下。" * 3, "短句"):
        bubble.set_text(text, auto_hide=False)
        assert window.geometry() == geometry  # Doro's window is untouched
        assert speech.isVisible() and speech.above
        assert window.floor_geometry().contains(speech.panel_geometry())
        assert speech.panel_geometry().bottom() < window.body_on_screen().top()
        bubble.clear_text()
        assert not speech.isVisible()
        assert window.geometry() == geometry


def test_changing_sprite_size_keeps_the_foot_not_center(pet):
    window, _, _, _ = pet
    place(window, 550, 799)
    foot = window.foot_position()
    for size in [(120, 300), (350, 130), (200, 200)]:
        window.view_model.set_sprite_size(QtCore.QSize(*size))
        window.on_sprite_renderer_changed()
        assert window.foot_position() == foot


def test_transparent_padding_is_not_the_floor(pet):
    window, _, sprite, _ = pet
    pixmap = QtGui.QPixmap(200, 200)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.fillRect(40, 20, 120, 130, QtCore.Qt.GlobalColor.red)
    painter.end()
    sprite.renderer.set_movie(SimpleNamespace(currentPixmap=lambda: pixmap, state=lambda: None))
    window.on_sprite_renderer_changed()
    place(window, 600, 799)
    assert window.sprite_contact_rect().height() == 130
    assert window.current_position().y() + window.sprite_contact_rect().bottom() == 799
    sprite.renderer.set_movie(None)


def test_negative_monitor_origin_and_taskbar_work_area(pet):
    window, bubble, _, _ = pet
    area = QtCore.QRect(-1920, -120, 1920, 1040)
    window._available_screen_geometry = lambda: area
    window.floor_geometry = lambda: area
    place(window, -900, area.bottom())
    bubble.set_text("另一個螢幕也要踩得到底。", auto_hide=False)
    assert window.foot_position() == QtCore.QPoint(-900, area.bottom())


def test_walking_with_different_gif_sizes_and_bubble_keeps_target(pet):
    window, bubble, _, _ = pet
    current = ["idle"]
    states = Mock()
    states.get_current_state.side_effect = lambda: SimpleNamespace(key=current[0])
    states.get_requested_state_key.side_effect = lambda: current[0]
    states.get_default_movement_state.return_value = "walk"
    states.get_move_state.return_value = None
    states.find_move_states_by_direction.return_value = []

    def switch(key, **_):
        current[0] = key
        window.view_model.set_sprite_size(
            QtCore.QSize(120, 270) if key == "walk" else QtCore.QSize(200, 200)
        )
        window.on_sprite_renderer_changed()
        return True

    states.set_state.side_effect = switch
    movement = MovementManager(window, states, MovementRepository(Path("/nonexistent")))
    place(window, 400, 400)
    before = window.foot_position()
    movement.handle_move_bracket("move:to;x=750;y=799", [])
    assert window.foot_position() == before
    for tick in range(500):
        if tick == 3:
            bubble.set_text("走到旁邊等你。", auto_hide=False)
        if tick == 8:
            bubble.clear_text()
        movement.process_active_movement(0.05)
        if not movement.has_active_movement:
            break
    assert not movement.has_active_movement
    assert window.foot_position() == QtCore.QPoint(750, 799)


@pytest.mark.parametrize("home_x", [0.0, 1.0])
def test_quiet_return_with_wider_walk_sprite_stops_at_screen_edge(pet, tmp_path, home_x):
    window, bubble, _, _ = pet
    config = ConfigManager(tmp_path / "edge.ini")
    config.update_ui(companion_home_x=home_x, companion_home_y=1.0)
    current = ["idle"]
    states = Mock()
    states.get_current_state.side_effect = lambda: SimpleNamespace(key=current[0])
    states.get_requested_state_key.side_effect = lambda: current[0]
    states.get_default_movement_state.return_value = "walk"
    states.get_move_state.return_value = None
    states.find_move_states_by_direction.return_value = []
    states.is_movement_only_state.return_value = False

    def switch(key, **_):
        current[0] = key
        window.view_model.set_sprite_size(
            QtCore.QSize(350, 200) if key == "walk" else QtCore.QSize(120, 200)
        )
        window.on_sprite_renderer_changed()
        return True

    states.set_state.side_effect = switch
    switch("idle")
    movement = MovementManager(window, states, MovementRepository(Path("/nonexistent")))
    movement.apply_directional_walk = Mock(wraps=movement.apply_directional_walk)
    window.seconds_since_last_activity = lambda: 100
    window.play_landing = Mock()
    controller = CompanionController(
        window=window,
        movement=movement,
        states=states,
        config=config,
        bubble=bubble,
        busy=lambda: movement.has_active_movement,
        cancel=Mock(),
        silence=Mock(),
    )
    place(window, 600, 799)
    controller.set_quiet(True)
    previous = window.foot_position()
    for _ in range(600):
        movement.process_active_movement(0.05)
        arrived = window.foot_position()
        # At normal walk speed each frame is small, including the last frame.
        assert (arrived - previous).manhattanLength() <= 30
        controller.tick(0.05)
        assert window.foot_position() == arrived
        previous = arrived
    assert not movement.has_active_movement
    movement.apply_directional_walk.assert_called_once()
    assert current[0] == "idle"
    assert abs(window.foot_position().x() - controller._home().x()) > 30
    window.play_landing.assert_not_called()


def test_bubble_follows_doro_and_flips_below_near_the_top(pet):
    window, bubble, _, speech = pet
    place(window, 600, 799)
    bubble.set_text("跟著我走。", auto_hide=False)
    offset = speech.panel_geometry().center() - window.body_on_screen().center()
    place(window, 300, 500)  # moving Doro moves the bubble with her
    assert speech.panel_geometry().center() - window.body_on_screen().center() == offset

    place(window, 300, window.sprite_contact_rect().height() + 5)  # no room above
    assert not speech.above
    assert speech.panel_geometry().top() > window.body_on_screen().bottom()
    assert window.floor_geometry().contains(speech.panel_geometry())


def test_bubble_hides_while_chat_history_is_expanded(pet):
    _, bubble, _, speech = pet
    bubble.set_text("聊天紀錄裡也有這句。", auto_hide=False)
    assert speech.isVisible()
    speech.set_suppressed(True)
    assert not speech.isVisible()
    speech.set_suppressed(False)
    assert speech.isVisible()


def test_bubble_lets_clicks_through(pet):
    *_, speech = pet
    assert speech.windowFlags() & QtCore.Qt.WindowType.WindowTransparentForInput


def test_short_wide_sprite_stays_inside_its_padded_window(pet):
    """A 200×60 lying pose gets a 200×120 window; the sprite must be centred in it,
    not pushed out by the old bubble-layout offset."""
    window, _, _, _ = pet
    place(window, 600, 799)
    foot = window.foot_position()
    window.view_model.set_sprite_size(QtCore.QSize(200, 60))
    window.on_sprite_renderer_changed()

    assert window.size() == QtCore.QSize(200, 120)
    assert QtCore.QRect(QtCore.QPoint(), window.size()).contains(window.sprite_contact_rect())
    assert window.foot_position() == foot


def test_bubble_repaints_when_only_the_state_changes(pet, monkeypatch):
    _, bubble, _, speech = pet
    bubble.set_text("同一句話。", auto_hide=False)
    repaints = []
    monkeypatch.setattr(speech, "update", lambda *a: repaints.append(a))

    speech._view_model.set_bubble_alpha(120)  # e.g. the new state has another alpha
    speech.refresh()

    assert repaints
