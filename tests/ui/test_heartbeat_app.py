"""Heartbeat wiring inside the real application, with isolated settings and files."""

from PySide6 import QtCore, QtWidgets

from doro_app.app import DoroApp
from doro_app.bootstrap import BootstrappedDependencies
from doro_app.core.action import ActionRepository, ActionService
from doro_app.core.automation.foreground_tracker import ForegroundTracker
from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.heartbeat.context import load_journal
from doro_app.core.llm import structured
from doro_app.core.llm.transport import Completion
from doro_app.core.movement.repository import MovementRepository
from doro_app.core.state import GifRepository
from doro_app.ui.theme.themed_menu import DoroMenu, build_context_menu_content
from doro_app.utils.config_manager import ConfigManager
from doro_app.utils.paths import STATE_DIR


def _app(tmp_path, real_state_service, monkeypatch):
    monkeypatch.setattr(ForegroundTracker, "start", lambda _: None)
    monkeypatch.setattr(DoroApp, "_maybe_build_a11y", lambda _: None)
    monkeypatch.setattr(DoroApp, "_maybe_build_automation", lambda _: None)
    monkeypatch.setattr(
        ChatOrchestrator, "_default_web_profile_dir", staticmethod(lambda: tmp_path / "web")
    )
    default_gif = STATE_DIR / "idle.gif"
    deps = BootstrappedDependencies(
        config_manager=ConfigManager(tmp_path / "settings.ini"),
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
    return DoroApp(deps=deps)


def test_heartbeat_menu_settings_and_interrupts(qtbot, tmp_path, real_state_service, monkeypatch):
    structured.forget_detected_modes()
    monkeypatch.setattr(
        structured.transport,
        "request_completion",
        lambda *_: Completion(
            '{"worth_saying":true,"state":null,"line":"休息一下吧","move":null}', None, 200
        ),
    )
    app = _app(tmp_path, real_state_service, monkeypatch)
    qtbot.addWidget(app.window)
    heartbeat = app._heartbeat
    try:
        app.window._timer.stop()
        app._idle_behavior._timer.stop()
        assert heartbeat.checklist_path == tmp_path / "heartbeat.md"
        assert not heartbeat.is_scheduled  # off by default

        callbacks = app._context_menu_ctrl._build_callbacks()
        menu = DoroMenu(app.window)
        build_context_menu_content(
            menu, app.window, app._context_menu_ctrl._build_snapshot(), callbacks
        )
        assert "立刻跳一次心跳" in {action.text() for action in menu.actions()}

        app._config_manager.update_ui(heartbeat_enabled=True, heartbeat_interval_minutes=7)
        app._on_companion_settings_changed()
        assert heartbeat.is_scheduled and heartbeat._timer.interval() == 7 * 60 * 1000

        # Focusing the chat bar delays a heartbeat; only sending a message cancels it.
        epoch = heartbeat._epoch
        app._interrupt_background_companionship()
        assert heartbeat._epoch == epoch
        app._chat_controller.request_started.emit("hi", False)
        assert heartbeat._epoch == epoch + 1
        app._companion.set_quiet(True)
        assert heartbeat._epoch == epoch + 2
        app._companion.set_quiet(False)

        app._chat_orchestrator.settings.set_server_url("http://127.0.0.1:9")
        spoken = []
        app._chat_orchestrator.bubble_text_requested.connect(lambda text, _o: spoken.append(text))
        QtWidgets.QApplication.processEvents()
        heartbeat._busy = lambda: False
        callbacks.heartbeat_now()
        qtbot.waitUntil(lambda: spoken == ["休息一下吧"], timeout=3000)
        assert load_journal(tmp_path / "heartbeat_journal.json")[0].line == "休息一下吧"
    finally:
        app._on_about_to_quit()
        structured.forget_detected_modes()
        QtCore.QCoreApplication.processEvents()
