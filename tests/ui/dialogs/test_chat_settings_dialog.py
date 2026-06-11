"""Tests for ChatSettingsDialog — simulate-response panel and a11y toggle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6 import QtCore


class _StubOrchestrator(QtCore.QObject):
    """Minimal chat_orchestrator stand-in exposing what the dialog uses."""

    def __init__(self, simulate_return=""):
        super().__init__()
        self.simulate_response = Mock(return_value=simulate_return)
        # Setters exercised by _on_save.
        for name in (
            "set_server_url", "set_model_name", "set_endpoint", "set_api_key",
            "set_temperature", "set_timeout", "set_max_stop_tokens", "set_stop_tokens",
        ):
            setattr(self, name, Mock())

    def get_server_url(self):
        return "http://localhost:1234"

    def get_model_name(self):
        return "mistral"

    def get_endpoint(self):
        return "/v1/chat/completions"

    def get_max_stop_tokens(self):
        return 0

    def get_api_key(self):
        return ""

    def get_temperature(self):
        return 0.7

    def get_timeout(self):
        return 30

    def get_stop_tokens(self):
        return []


class _StubConfigManager:
    def __init__(
        self,
        a11y_enabled=False,
        mouse_enabled=False,
        a11y_share_input_values=False,
    ):
        self.automation = SimpleNamespace(
            a11y_enabled=a11y_enabled,
            mouse_enabled=mouse_enabled,
            a11y_share_input_values=a11y_share_input_values,
        )
        self.update_automation = Mock()
        self.save = Mock()


class _StubCoreManager:
    def __init__(self, orchestrator, config_manager, a11y_service=None):
        self.chat_orchestrator = orchestrator
        self.config_manager = config_manager
        self.a11y_service = a11y_service


def _make_dialog(qtbot, simulate_return="", a11y_enabled=False, a11y_service=None):
    from doro_app.ui.dialogs.chat_settings_dialog import ChatSettingsDialog

    orch = _StubOrchestrator(simulate_return=simulate_return)
    config = _StubConfigManager(a11y_enabled=a11y_enabled)
    dialog = ChatSettingsDialog(_StubCoreManager(orch, config, a11y_service))
    qtbot.addWidget(dialog)
    return dialog, orch, config


def test_simulate_injects_typed_text(qtbot):
    dialog, orch, _ = _make_dialog(qtbot, simulate_return="你好呀")
    dialog._test_input.setPlainText("你好呀！[MOVE:dir=right]")

    dialog._on_simulate()

    orch.simulate_response.assert_called_once_with("你好呀！[MOVE:dir=right]")
    assert "你好呀" in dialog._test_output.text()


def test_empty_input_does_not_call_simulate(qtbot):
    dialog, orch, _ = _make_dialog(qtbot)
    dialog._test_input.setPlainText("   ")

    dialog._on_simulate()

    orch.simulate_response.assert_not_called()
    assert "請先輸入" in dialog._test_output.text()


def test_actions_only_reply_reports_no_dialogue(qtbot):
    dialog, orch, _ = _make_dialog(qtbot, simulate_return="")
    dialog._test_input.setPlainText("[MOVE:dir=right]")

    dialog._on_simulate()

    orch.simulate_response.assert_called_once_with("[MOVE:dir=right]")
    assert "沒有對話" in dialog._test_output.text()


def test_a11y_checkbox_reflects_config(qtbot):
    on_dialog, _, _ = _make_dialog(qtbot, a11y_enabled=True)
    assert on_dialog._a11y_checkbox.isChecked() is True

    off_dialog, _, _ = _make_dialog(qtbot, a11y_enabled=False)
    assert off_dialog._a11y_checkbox.isChecked() is False


def test_save_persists_a11y_toggle(qtbot):
    dialog, _, config = _make_dialog(qtbot, a11y_enabled=False)
    dialog._a11y_checkbox.setChecked(True)

    dialog._on_save()

    config.update_automation.assert_called_once_with(
        a11y_enabled=True,
        a11y_share_input_values=False,
        mouse_enabled=False,
    )
    config.save.assert_called_once()


def test_save_persists_share_input_values_when_a11y_on(qtbot):
    dialog, _, config = _make_dialog(qtbot, a11y_enabled=False)
    dialog._a11y_checkbox.setChecked(True)
    dialog._a11y_share_values_checkbox.setChecked(True)

    dialog._on_save()

    config.update_automation.assert_called_once_with(
        a11y_enabled=True,
        a11y_share_input_values=True,
        mouse_enabled=False,
    )


def test_save_drops_share_input_values_when_a11y_off(qtbot):
    dialog, _, config = _make_dialog(
        qtbot, a11y_enabled=True
    )
    # User unchecks a11y but the share-values checkbox is still ticked:
    # the persisted value must be False because the dependency is gone.
    dialog._a11y_share_values_checkbox.setChecked(True)
    dialog._a11y_checkbox.setChecked(False)

    dialog._on_save()

    config.update_automation.assert_called_once_with(
        a11y_enabled=False,
        a11y_share_input_values=False,
        mouse_enabled=False,
    )


def test_save_enabling_a11y_clears_session_blacklist(qtbot):
    service = Mock()
    dialog, _, _ = _make_dialog(qtbot, a11y_enabled=False, a11y_service=service)
    dialog._a11y_checkbox.setChecked(True)

    dialog._on_save()

    service.clear_session_blacklist.assert_called_once()


def test_save_without_a11y_does_not_clear_blacklist(qtbot):
    service = Mock()
    dialog, _, _ = _make_dialog(qtbot, a11y_enabled=False, a11y_service=service)
    dialog._a11y_checkbox.setChecked(False)

    dialog._on_save()

    service.clear_session_blacklist.assert_not_called()


def test_preview_shows_tree_on_success(qtbot):
    service = Mock()
    service.diagnose_foreground_tree.return_value = (True, 'button "OK" (10,20 30x40)')
    dialog, _, _ = _make_dialog(qtbot, a11y_service=service)

    dialog._run_a11y_preview()

    assert 'button "OK"' in dialog._a11y_output.toPlainText()


def test_preview_shows_reason_on_failure(qtbot):
    service = Mock()
    service.diagnose_foreground_tree.return_value = (False, "a11y 未啟用（請在設定勾選）")
    dialog, _, _ = _make_dialog(qtbot, a11y_service=service)

    dialog._run_a11y_preview()

    assert "未啟用" in dialog._a11y_output.toPlainText()


def test_preview_handles_missing_service(qtbot):
    dialog, _, _ = _make_dialog(qtbot, a11y_service=None)

    dialog._run_a11y_preview()

    assert "未建立" in dialog._a11y_output.toPlainText()
