"""Exercise real application wiring with isolated settings and resource stores."""

from unittest.mock import Mock

from PySide6 import QtCore, QtWidgets

from doro_app.app import DoroApp
from doro_app.bootstrap import BootstrappedDependencies
from doro_app.core.action import ActionRepository, ActionService
from doro_app.core.automation.foreground_tracker import ForegroundTracker
from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.movement.repository import MovementRepository
from doro_app.core.state import GifRepository
from doro_app.ui.theme.themed_menu import DoroMenu, build_context_menu_content
from doro_app.utils.config_manager import ConfigManager
from doro_app.utils.paths import STATE_DIR


def test_quiet_menu_gates_background_but_keeps_explicit_interaction(
    qtbot, tmp_path, real_state_service, monkeypatch
):
    monkeypatch.setattr(ForegroundTracker, "start", lambda _: None)
    monkeypatch.setattr(DoroApp, "_maybe_build_a11y", lambda _: None)
    monkeypatch.setattr(DoroApp, "_maybe_build_automation", lambda _: None)
    monkeypatch.setattr(
        ChatOrchestrator, "_default_web_profile_dir", staticmethod(lambda: tmp_path / "web")
    )
    config = ConfigManager(tmp_path / "settings.ini")
    # Simulate upgrading a user who had the removed floor option enabled.
    config.update_ui(companion_floor_interaction=True)
    config.save()
    config = ConfigManager(tmp_path / "settings.ini")
    default_gif = STATE_DIR / "idle.gif"
    deps = BootstrappedDependencies(
        config_manager=config,
        state_service=real_state_service,
        movement_repo=MovementRepository(tmp_path / "movements.json"),
        action_service=ActionService(
            ActionRepository(tmp_path / "actions.json"),
            real_state_service,
            GifRepository(tmp_path / "sprites"),
            default_idle_gif=default_gif,
        ),
        default_idle_gif=default_gif,
        prompt_file_path=tmp_path / "prompt.txt",
        click_actions_path=tmp_path / "click.txt",
    )
    app = DoroApp(deps=deps)
    qtbot.addWidget(app.window)
    try:
        app.window._timer.stop()
        app._idle_behavior._timer.stop()
        area = QtCore.QRect(0, 0, 1200, 800)
        app.window._available_screen_geometry = lambda: area
        app.window.floor_geometry = lambda: area
        app.run()
        app._movement.place_foot(QtCore.QPoint(600, 400))
        callbacks = app._context_menu_ctrl._build_callbacks()
        callbacks.save_nest()
        callbacks.save_rest_state()
        callbacks.toggle_quiet(True)
        assert app._context_menu_ctrl._build_snapshot().quiet_companion
        assert app._presence._quiet

        app._idle_behavior._do_speak = Mock()
        app._idle_behavior._do_move = Mock()
        app._idle_behavior._do_transition = Mock()
        app._idle_behavior._do_walk_and_speak = Mock()
        app._idle_behavior._on_timer()
        app._idle_behavior._do_speak.assert_not_called()
        app._idle_behavior._do_move.assert_not_called()
        app._idle_behavior._do_transition.assert_not_called()
        app._idle_behavior._do_walk_and_speak.assert_not_called()

        # Explicit speech is still available and cannot dislodge her feet.
        foot = app.window.foot_position()
        app._chat_orchestrator.speak_line("我在這裡。")
        assert app._bubble_controller.text == "我在這裡。"
        assert app.window.foot_position() == foot
        app._bubble_controller.clear_text()
        app._companion.tick(0.02)
        assert app.window.foot_position() == foot

        # A saved point in mid-screen must stay there, including after walking.
        app.window.seconds_since_last_activity = lambda: 100
        app._movement.place_foot(QtCore.QPoint(900, 600))
        for _ in range(500):
            app._movement.process_active_movement(0.05)
            app._companion.tick(0.05)
        assert not app._movement.has_active_movement
        assert app.window.foot_position() == QtCore.QPoint(600, 400)

        # Modal preferences must pause returns as well as idle wandering.
        preferences = QtWidgets.QDialog(app.window)
        qtbot.addWidget(preferences)
        preferences.setModal(True)
        preferences.show()
        QtWidgets.QApplication.processEvents()
        assert app._companion_busy()
        app._movement.place_foot(QtCore.QPoint(700, 450))
        app._companion.tick(0.05)
        assert not app._movement.has_active_movement
        assert app.window.foot_position() == QtCore.QPoint(700, 450)
        preferences.close()

        snapshot = app._context_menu_ctrl._build_snapshot()
        assert snapshot.has_rest_point
        menu = DoroMenu(app.window)
        build_context_menu_content(menu, app.window, snapshot, callbacks)
        actions = {action.text(): action for action in menu.actions()}
        assert "把這裡設為休息點" in actions
        assert "陪伴設定…" in actions
        assert not any("底部互動" in label for label in actions)
        actions["清除休息點（原地陪伴）"].trigger()
        assert not app._context_menu_ctrl._build_snapshot().has_rest_point
        app._movement.place_foot(QtCore.QPoint(600, 750))
        app._companion.released()
        app._companion.tick(0.5)
        assert app.window.foot_position() == QtCore.QPoint(600, 750)
        callbacks.toggle_quiet(False)
        assert not app._presence._quiet
        assert not config.ui.quiet_companion
    finally:
        app._idle_behavior._timer.stop()
        app._on_about_to_quit()
        app.window.close()
