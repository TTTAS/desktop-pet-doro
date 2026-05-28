"""Tests for ChatSettingsDialog — focus on the simulate-response test panel."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6 import QtCore


class _StubOrchestrator(QtCore.QObject):
    """Minimal chat_orchestrator stand-in exposing what the dialog reads."""

    def __init__(self, simulate_return=""):
        super().__init__()
        self.simulate_response = Mock(return_value=simulate_return)

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


class _StubCoreManager:
    def __init__(self, orchestrator):
        self.chat_orchestrator = orchestrator


def _make_dialog(qtbot, simulate_return=""):
    from doro_app.ui.dialogs.chat_settings_dialog import ChatSettingsDialog

    orch = _StubOrchestrator(simulate_return=simulate_return)
    dialog = ChatSettingsDialog(_StubCoreManager(orch))
    qtbot.addWidget(dialog)
    return dialog, orch


def test_simulate_injects_typed_text(qtbot):
    dialog, orch = _make_dialog(qtbot, simulate_return="你好呀")
    dialog._test_input.setPlainText("你好呀！[MOVE:dir=right]")

    dialog._on_simulate()

    orch.simulate_response.assert_called_once_with("你好呀！[MOVE:dir=right]")
    assert "你好呀" in dialog._test_output.text()


def test_empty_input_does_not_call_simulate(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._test_input.setPlainText("   ")

    dialog._on_simulate()

    orch.simulate_response.assert_not_called()
    assert "請先輸入" in dialog._test_output.text()


def test_actions_only_reply_reports_no_dialogue(qtbot):
    dialog, orch = _make_dialog(qtbot, simulate_return="")
    dialog._test_input.setPlainText("[MOVE:dir=right]")

    dialog._on_simulate()

    orch.simulate_response.assert_called_once_with("[MOVE:dir=right]")
    assert "沒有對話" in dialog._test_output.text()
