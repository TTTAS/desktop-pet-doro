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
    bubble.text_changed.connect(lambda *_: window.apply_window_preferred_size())
    sprite.sprite_renderer_changed.connect(window.on_sprite_renderer_changed)
    window.apply_window_preferred_size()
    window.show()
    yield window, bubble, sprite
    bubble.clear_text()
    window.close()


def place(window, x, y):
    window.move_window_to(
        window.clamp_window_position(QtCore.QPoint(x, y) - window.sprite_foot_offset_logical())
    )


@pytest.mark.parametrize("x", [110, 600, 1090])
def test_bubble_toggle_does_not_lift_feet_or_clip_panel(pet, x):
    window, bubble, _ = pet
    place(window, x, 799)
    foot = window.foot_position()
    for text in ("我在這裡陪你。", "先忙你的事情，我在旁邊休息一下。" * 3, "短句"):
        bubble.set_text(text, auto_hide=False)
        assert window.foot_position() == foot
        window.grab()  # Execute the real painter and inspect its resulting panel.
        panel = window._panel_rect_cache.translated(window.current_position()).toAlignedRect()
        assert window.floor_geometry().contains(panel)
        assert panel.bottom() < window.foot_position().y()
        bubble.clear_text()
        assert window.foot_position() == foot


def test_changing_sprite_size_keeps_the_foot_not_center(pet):
    window, _, _ = pet
    place(window, 550, 799)
    foot = window.foot_position()
    for size in [(120, 300), (350, 130), (200, 200)]:
        window.view_model.set_sprite_size(QtCore.QSize(*size))
        window.on_sprite_renderer_changed()
        assert window.foot_position() == foot


def test_transparent_padding_is_not_the_floor(pet):
    window, _, sprite = pet
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
    window, bubble, _ = pet
    area = QtCore.QRect(-1920, -120, 1920, 1040)
    window._available_screen_geometry = lambda: area
    window.floor_geometry = lambda: area
    place(window, -900, area.bottom())
    bubble.set_text("另一個螢幕也要踩得到底。", auto_hide=False)
    assert window.foot_position() == QtCore.QPoint(-900, area.bottom())


def test_walking_with_different_gif_sizes_and_bubble_keeps_target(pet):
    window, bubble, _ = pet
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
    window, bubble, _ = pet
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


def test_bubble_resize_never_paints_before_the_window_is_back_in_place(pet):
    """Resize and move are separate steps; a paint between them showed Doro
    "teleporting" away and back whenever the speech bubble appeared or hid."""
    window, bubble, _ = pet
    place(window, 600, 799)
    painted = []

    class PaintSpy(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Type.Paint:
                painted.append(obj.geometry())
            return False

    spy = PaintSpy()
    window.installEventFilter(spy)
    for text in ("人～好多程式碼喔，doro看不太懂耶～" * 2, ""):
        painted.clear()
        before = window.geometry()
        if text:
            bubble.set_text(text, auto_hide=False)
        else:
            bubble.clear_text()
        assert window.geometry() != before  # the window really resized and moved
        assert painted, "the final layout is painted right away"
        assert set(painted) == {window.geometry()}  # every paint at the final geometry
    window.removeEventFilter(spy)
