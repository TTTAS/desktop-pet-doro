"""Tests for the a11y entries in the right-click context menu."""

from __future__ import annotations

import dataclasses
from unittest.mock import Mock

from PySide6 import QtWidgets

from doro_app.ui.components.context_menu_controller import ContextMenuController
from doro_app.ui.theme.themed_menu import (
    DoroMenu,
    MenuCallbacks,
    MenuSnapshot,
    build_context_menu_content,
)


def _all_actions(menu):
    out = []
    for action in menu.actions():
        out.append(action)
        if action.menu() is not None:
            out.extend(_all_actions(action.menu()))
    return out


def _find(menu, text):
    for action in _all_actions(menu):
        if action.text() == text:
            return action
    return None


def _snapshot(a11y_enabled=False):
    return MenuSnapshot(
        visible_states=[],
        current_state_key="idle",
        is_topmost=False,
        bubble_visible=False,
        is_chat_inflight=False,
        has_chat_history=False,
        a11y_enabled=a11y_enabled,
    )


def _callbacks():
    return MenuCallbacks(**{f.name: Mock() for f in dataclasses.fields(MenuCallbacks)})


def test_menu_opens_asset_factory(qtbot):
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    menu = DoroMenu(window)
    callbacks = _callbacks()
    build_context_menu_content(menu, window, _snapshot(), callbacks)
    _find(menu, "素材工廠（影片去背）…").trigger()
    callbacks.show_asset_factory.assert_called_once()


def test_menu_has_a11y_toggle_reflecting_snapshot(qtbot):
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    menu = DoroMenu(window)
    cbs = _callbacks()

    build_context_menu_content(menu, window, _snapshot(a11y_enabled=True), cbs)
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]  # keep alive
    assert submenus

    toggle = _find(menu, "讓 Doro 看畫面（無障礙樹）")
    assert toggle is not None
    assert toggle.isCheckable()
    assert toggle.isChecked() is True

    toggle.trigger()
    cbs.toggle_a11y.assert_called_once()


def test_menu_has_preview_action(qtbot):
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    menu = DoroMenu(window)
    cbs = _callbacks()

    build_context_menu_content(menu, window, _snapshot(), cbs)
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]  # keep alive
    assert submenus

    preview = _find(menu, "預覽 Doro 看到什麼")
    assert preview is not None

    preview.trigger()
    cbs.preview_a11y.assert_called_once()


def test_menu_has_simulate_response_action(qtbot):
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    menu = DoroMenu(window)
    cbs = _callbacks()

    build_context_menu_content(menu, window, _snapshot(), cbs)
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]  # keep alive
    assert submenus

    simulate = _find(menu, "假傳伺服器回應（測試）")
    assert simulate is not None

    simulate.trigger()
    cbs.simulate_response.assert_called_once()


class _FakeReplyDialog:
    """Stands in for SimulateReplyDialog so no modal loop runs."""

    reply = '{"line":"幫人點～","move":{"x":180,"y":100},"tool":{"kind":"click"}}'
    accepted = True

    def __init__(self, state_keys, parent=None):
        _FakeReplyDialog.state_keys = state_keys

    def exec(self):
        return self.accepted

    def reply_json(self):
        return self.reply if self.accepted else None


def test_simulate_response_feeds_orchestrator(monkeypatch):
    from doro_app.ui.dialogs import simulate_reply_dialog

    monkeypatch.setattr(simulate_reply_dialog, "SimulateReplyDialog", _FakeReplyDialog)
    monkeypatch.setattr(_FakeReplyDialog, "accepted", True)
    core = Mock()
    ctrl = _make_controller(core)
    ctrl._state_service.visible_state_keys.return_value = ["idle", "happy"]

    ctrl._simulate_response()

    assert _FakeReplyDialog.state_keys == ["idle", "happy"]
    core.chat_orchestrator.simulate_response.assert_called_once_with(_FakeReplyDialog.reply)


def test_simulate_response_cancelled_does_nothing(monkeypatch):
    from doro_app.ui.dialogs import simulate_reply_dialog

    monkeypatch.setattr(simulate_reply_dialog, "SimulateReplyDialog", _FakeReplyDialog)
    monkeypatch.setattr(_FakeReplyDialog, "accepted", False)
    core = Mock()
    ctrl = _make_controller(core)
    ctrl._state_service.visible_state_keys.return_value = []
    ctrl._simulate_response()
    core.chat_orchestrator.simulate_response.assert_not_called()


def test_toggle_a11y_persists():
    core = Mock()
    ctrl = ContextMenuController(
        window=Mock(),
        state_service=Mock(),
        state_controller=Mock(),
        dialog_manager=Mock(),
        bubble_controller=Mock(),
        core_manager=core,
        chat_ui=Mock(),
    )

    ctrl._toggle_a11y(True)

    core.config_manager.update_automation.assert_called_once_with(a11y_enabled=True)
    core.config_manager.save.assert_called_once()


def test_toggle_mouse_enabled_persists():
    """Flipping the mouse-click toggle writes config + saves. The runtime
    self-gate inside `AutomationManager.execute_click` reads the flag on
    every click attempt, so no restart wiring is needed here."""
    core = Mock()
    ctrl = ContextMenuController(
        window=Mock(),
        state_service=Mock(),
        state_controller=Mock(),
        dialog_manager=Mock(),
        bubble_controller=Mock(),
        core_manager=core,
        chat_ui=Mock(),
    )

    ctrl._toggle_mouse_enabled(True)

    core.config_manager.update_automation.assert_called_once_with(mouse_enabled=True)
    core.config_manager.save.assert_called_once()


def _make_controller(core):
    return ContextMenuController(
        window=Mock(),
        state_service=Mock(),
        state_controller=Mock(),
        dialog_manager=Mock(),
        bubble_controller=Mock(),
        core_manager=core,
        chat_ui=Mock(),
    )


def test_toggle_on_clears_session_blacklist():
    core = Mock()
    _make_controller(core)._toggle_a11y(True)
    core.a11y_service.clear_session_blacklist.assert_called_once()


def test_toggle_off_does_not_clear_session_blacklist():
    core = Mock()
    _make_controller(core)._toggle_a11y(False)
    core.a11y_service.clear_session_blacklist.assert_not_called()


def test_show_a11y_result_success(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda parent, title, text: captured.update(title=title, text=text),
    )
    service = Mock()
    service.diagnose_foreground_tree.return_value = (True, 'button "OK" (1,2 3x4)')
    ctrl = ContextMenuController(
        window=Mock(),
        state_service=Mock(),
        state_controller=Mock(),
        dialog_manager=Mock(),
        bubble_controller=Mock(),
        core_manager=Mock(),
        chat_ui=Mock(),
    )

    ctrl._show_a11y_result(service)

    assert captured["title"] == "Doro 現在看到"
    assert 'button "OK"' in captured["text"]


def test_preview_a11y_reads_immediately(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda parent, title, text: captured.update(title=title, text=text),
    )
    service = Mock()
    service.diagnose_foreground_tree.return_value = (True, 'button "OK" (1,2 3x4)')
    core = Mock()
    core.a11y_service = service
    ctrl = _make_controller(core)

    ctrl._preview_a11y()

    service.diagnose_foreground_tree.assert_called_once()
    assert captured["title"] == "Doro 現在看到"
    assert 'button "OK"' in captured["text"]


def test_preview_a11y_handles_missing_service(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda parent, title, text: captured.update(title=title, text=text),
    )
    core = Mock()
    core.a11y_service = None
    ctrl = _make_controller(core)

    ctrl._preview_a11y()

    assert "未建立" in captured["text"]


def test_show_a11y_result_failure(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda parent, title, text: captured.update(title=title, text=text),
    )
    service = Mock()
    service.diagnose_foreground_tree.return_value = (False, "a11y 未啟用")
    ctrl = ContextMenuController(
        window=Mock(),
        state_service=Mock(),
        state_controller=Mock(),
        dialog_manager=Mock(),
        bubble_controller=Mock(),
        core_manager=Mock(),
        chat_ui=Mock(),
    )

    ctrl._show_a11y_result(service)

    assert captured["title"] == "目前讀不到內容"
    assert "未啟用" in captured["text"]
