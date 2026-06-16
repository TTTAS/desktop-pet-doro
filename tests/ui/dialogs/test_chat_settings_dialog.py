"""Tests for ChatSettingsDialog — a11y toggle, settings persistence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from PySide6 import QtCore


class _StubOrchestrator(QtCore.QObject):
    """Minimal chat_orchestrator stand-in exposing what the dialog uses."""

    def __init__(self):
        super().__init__()
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
    def __init__(
        self,
        orchestrator,
        config_manager,
        a11y_service=None,
        automation_manager=None,
    ):
        self.chat_orchestrator = orchestrator
        self.config_manager = config_manager
        self.a11y_service = a11y_service
        self.automation_manager = automation_manager


def _make_dialog(
    qtbot,
    a11y_enabled=False,
    a11y_service=None,
    automation_manager=None,
    mouse_enabled=False,
):
    from doro_app.ui.dialogs.chat_settings_dialog import ChatSettingsDialog

    orch = _StubOrchestrator()
    config = _StubConfigManager(
        a11y_enabled=a11y_enabled, mouse_enabled=mouse_enabled
    )
    dialog = ChatSettingsDialog(
        _StubCoreManager(
            orch,
            config,
            a11y_service,
            automation_manager=automation_manager,
        )
    )
    qtbot.addWidget(dialog)
    return dialog, orch, config


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
