"""Tests for ChatSettingsDialog — focus on the server-response test panel."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6 import QtCore


class _StubOrchestrator(QtCore.QObject):
    """Minimal chat_orchestrator stand-in exposing what the dialog reads."""

    test_result = QtCore.Signal(str, str)

    def __init__(self):
        super().__init__()
        self.send_test_request = Mock()

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


def _make_dialog(qtbot):
    from doro_app.ui.dialogs.chat_settings_dialog import ChatSettingsDialog

    orch = _StubOrchestrator()
    dialog = ChatSettingsDialog(_StubCoreManager(orch))
    qtbot.addWidget(dialog)
    return dialog, orch


def test_test_button_sends_request_with_form_overrides(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._test_input.setText("測試一下")

    dialog._on_test()

    orch.send_test_request.assert_called_once()
    args, kwargs = orch.send_test_request.call_args
    assert args[0] == "測試一下"
    assert kwargs["server_url"] == "http://localhost:1234"
    assert kwargs["endpoint_path"] == "/v1/chat/completions"
    assert kwargs["model"] == "mistral"
    # Button disabled and a pending indicator shown while the request runs.
    assert dialog._test_btn.isEnabled() is False
    assert "傳送中" in dialog._test_output.toPlainText()


def test_empty_input_falls_back_to_default_message(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._test_input.setText("   ")

    dialog._on_test()

    assert orch.send_test_request.call_args[0][0] == "你好"


def test_result_shows_raw_text_including_control_tags(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._on_test()

    orch.test_result.emit("早安！[MOVE:dir=right]", "")

    assert dialog._test_btn.isEnabled() is True
    assert "[MOVE:dir=right]" in dialog._test_output.toPlainText()


def test_result_shows_error_message(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._on_test()

    orch.test_result.emit("", "Network error: connection refused")

    assert dialog._test_btn.isEnabled() is True
    text = dialog._test_output.toPlainText()
    assert "錯誤" in text
    assert "connection refused" in text


def test_result_handles_empty_response(qtbot):
    dialog, orch = _make_dialog(qtbot)
    dialog._on_test()

    orch.test_result.emit("", "")

    assert "未回傳" in dialog._test_output.toPlainText()
