"""Bubble wiring in the real application: progress bubbles can be cleared, and every
background speaker sees a visible bubble as busy."""

from PySide6 import QtCore

from tests.ui.test_heartbeat_app import _app, _close


def test_clear_request_reaches_the_bubble_and_reactions_see_it(
    qtbot, tmp_path, real_state_service, monkeypatch
):
    app = _app(tmp_path, real_state_service, monkeypatch)
    qtbot.addWidget(app.window)
    try:
        app.window._timer.stop()
        app._idle_behavior._timer.stop()
        orch = app._chat_orchestrator
        orch._on_request_started("auto", True)
        assert app._bubble_controller.text == "Thinking..."
        assert app._presence._bubble_busy()
        assert app._heartbeat._busy()

        orch._on_request_failed("network down", True)

        assert app._bubble_controller.text == ""
        assert not app._presence._bubble_busy()
    finally:
        _close(app)
        QtCore.QCoreApplication.processEvents()
