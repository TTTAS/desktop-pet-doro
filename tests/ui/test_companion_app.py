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
from doro_app.ui.dialogs.companion_dialog import CompanionDialog
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
    config.save()
    config._settings.setValue("ui/companion_floor_interaction", True)
    config._settings.sync()
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
        real_state_service.add_state("manual_pose", "手動姿勢")
        for import_gif in [False, True]:
            # Drive the real menu callback and dialog save without a nested UI loop.
            def accept_preferences(dialog, import_gif=import_gif):
                if import_gif:
                    dialog._pending_gif = default_gif
                else:
                    dialog.rest_state.setCurrentIndex(dialog.rest_state.findData("manual_pose"))
                dialog.accept()
                return dialog.result()

            foot = app.window.foot_position()
            with monkeypatch.context() as patch:
                patch.setattr(CompanionDialog, "exec", accept_preferences)
                callbacks.show_companion_settings()
            assert real_state_service.get_current_state_key() == config.ui.companion_rest_state
            assert app.window.foot_position() == foot
            assert not app._movement.has_active_movement

        app._interrupt_background_companionship()
        callbacks.set_state("manual_pose")
        for _ in range(10):
            app._companion.tick(0.05)
        assert real_state_service.get_current_state_key() == "manual_pose"
        app._companion.interrupt()
        app._companion.tick(0.05)
        assert real_state_service.get_current_state_key() == config.ui.companion_rest_state
        callbacks.toggle_quiet(False)
        assert not app._presence._quiet
        assert not config.ui.quiet_companion

        # The launcher is nonmodal; both menu entries reuse one floating window.
        floating = app._chat_ui._chat_dialog
        assert floating.isVisible() and not floating.expanded
        callbacks.prompt_chat()
        assert floating.expanded and not floating.isModal()
        assert app._companion_busy()
        app._idle_behavior._on_timer()
        app._idle_behavior._do_move.assert_not_called()
        floating.input.setPlainText("陪我聊聊")

        def send_chat(text, **kwargs):
            assert text == "陪我聊聊"
            assert kwargs == {"silent": True, "is_auto": False}
            app._chat_orchestrator.bubble_text_requested.emit("我在這裡陪你。", {})
            return True

        with monkeypatch.context() as patch:
            patch.setattr(app._chat_orchestrator, "send_message", send_chat)
            floating.send()
        assert floating._messages[-2:] == [("你", "陪我聊聊"), ("Doro", "我在這裡陪你。")]
        assert floating.expanded
        app._chat_controller.request_failed.emit("offline", False)
        assert floating.input.toPlainText() == "陪我聊聊"
        floating.close()
        assert not app._floating_chat_open()
        callbacks.prompt_chat()
        assert app._chat_ui._chat_dialog is floating
        with monkeypatch.context() as patch:
            patch.setattr(
                QtWidgets.QMessageBox,
                "question",
                lambda *_: QtWidgets.QMessageBox.StandardButton.Yes,
            )
            app._chat_ui.clear_chat_history()
        assert not floating._messages
        floating.collapse()
    finally:
        app._idle_behavior._timer.stop()
        app._on_about_to_quit()
        app.window.close()
