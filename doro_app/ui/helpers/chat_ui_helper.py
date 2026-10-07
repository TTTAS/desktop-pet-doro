"""Chat UI helper - handles all chat-related menu actions and dialogs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from ..dialogs.floating_chat import FloatingChatWindow

if TYPE_CHECKING:
    from ...core.core_manager import CoreManager
    from ..components.bubble_controller import BubbleController
    from ..window import DoroWindow

_PROVIDER_PRESETS = {
    "Local (LMStudio)": {
        "server_url": "http://127.0.0.1:1234",
        "model": "lmstudio",
        "endpoint_path": "/v1/chat/completions",
        "max_stop_tokens": 0,
    },
    "Gemini": {
        "server_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "endpoint_path": "/chat/completions",
        "max_stop_tokens": 5,
    },
}


class ChatUIHelper:
    """
    Handles chat-related UI interactions for DoroWindow.

    This helper extracts chat configuration dialogs and menu actions
    to reduce the complexity of the main window class.
    """

    def __init__(
        self,
        window: DoroWindow,
        core_manager: CoreManager,
        bubble_controller: BubbleController,
        on_interaction=None,
    ) -> None:
        self.window = window
        self._core_manager = core_manager
        # ChatSettingsDialog is heavy to build (translucent frameless QDialog
        # + 6-layer antialiased shadow + Qt stylesheet parse). Cache it after
        # first construction so subsequent opens are instant.
        self._settings_dialog = None
        self._chat_dialog = None
        self._bubble_controller = bubble_controller
        self._on_interaction = on_interaction or (lambda: None)

    @property
    def _chat(self):
        """Shortcut to the chat orchestrator."""
        return self._core_manager.chat_orchestrator

    def prompt_chat(self) -> None:
        """Expand the reusable nonmodal chat window."""
        self._ensure_chat().expand()

    @property
    def chat_open(self) -> bool:
        return self._chat_dialog is not None and self._chat_dialog.expanded

    def _ensure_chat(self) -> FloatingChatWindow:
        if self._chat_dialog is None:
            self._chat_dialog = FloatingChatWindow(self._send, self.window)
            self._chat_dialog.interaction.connect(self._interact)
            self._chat_dialog.expanded_changed.connect(lambda _: self.window.mark_user_activity())
            self._chat_dialog.settings_requested.connect(self.open_settings_dialog)
            self._core_manager.chat_response_received.connect(self._chat_dialog.receive_reply)
            self._core_manager.chat_operation_completed.connect(self._chat_dialog.finish_processing)
        return self._chat_dialog

    def _interact(self):
        self.window.mark_user_activity()
        self._on_interaction()

    def _send(self, text: str) -> bool:
        # Busy rejection is shown inline; web-operation confirmations still
        # pass through the orchestrator's existing routing and safeguards.
        return self._core_manager.send_chat_message(text, silent=True, is_auto=False)

    def show_launcher(self):
        dialog = self._ensure_chat()
        body = self.window.sprite_contact_rect().translated(self.window.current_position())
        anchor = QtCore.QPoint(body.right() + 12, body.top())
        area = self.window.floor_geometry()
        if anchor.x() + dialog.width() > area.right():
            anchor.setX(body.left() - dialog.width() - 12)
        dialog.show_launcher(anchor)

    def request_failed(self, error: str, was_auto: bool):
        if self._chat_dialog is not None:
            self._chat_dialog.request_failed(error, was_auto)

    def shutdown(self):
        if self._chat_dialog is not None:
            self._chat_dialog.hide()

    def clear_chat_history(self) -> None:
        """Clear chat history after confirmation."""
        reply = QtWidgets.QMessageBox.question(
            self.window,
            "清除對話紀錄",
            "確定要清除所有對話紀錄嗎？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._chat.clear_history()
            self._bubble_controller.clear_text()
            if self._chat_dialog is not None:
                self._chat_dialog.clear_history()

    def edit_chat_prompt(self) -> None:
        """Edit the chat system prompt."""
        current_prompt = self._chat.settings.system_prompt

        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self.window,
            "編輯人設",
            "Doro 的人設（性格與語氣；回覆格式由程式負責，不必寫在這裡）:",
            current_prompt,
        )
        if not ok:
            return

        self._chat.settings.update_system_prompt(text)
        QtWidgets.QMessageBox.information(
            self.window,
            "人設已更新",
            "人設已成功更新",
        )

    def configure_chat_server(self) -> None:
        """Configure chat server URL."""
        current = self._chat.settings.server_url
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定聊天伺服器",
            "伺服器 URL:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            self._chat.settings.set_server_url(text.strip())

    def configure_chat_model(self) -> None:
        """Configure chat model name."""
        current = self._chat.settings.model
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定模型",
            "模型名稱:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            self._chat.settings.set_model(text.strip())

    def configure_chat_endpoint(self) -> None:
        """Configure chat API endpoint."""
        current = self._chat.settings.endpoint_path
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定 API 端點",
            "API 端點路徑:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            self._chat.settings.set_endpoint_path(text.strip())

    def configure_chat_temperature(self) -> None:
        """Configure chat temperature parameter."""
        current = self._chat.settings.temperature
        value, ok = QtWidgets.QInputDialog.getDouble(
            self.window,
            "設定 Temperature",
            "Temperature (0.0 - 2.0):",
            current,
            0.0,
            2.0,
            2,
        )
        if ok:
            self._chat.settings.set_temperature(value)

    def configure_chat_timeout(self) -> None:
        """Configure chat request timeout."""
        current = self._chat.settings.timeout_seconds
        value, ok = QtWidgets.QInputDialog.getInt(
            self.window,
            "設定請求逾時",
            "逾時秒數:",
            current,
            1,
            300,
        )
        if ok:
            self._chat.settings.set_timeout_seconds(value)

    def configure_stop_tokens(self) -> None:
        """Configure stop tokens (one per line)."""
        current = self._chat.settings.stop_tokens
        display = "\n".join(t.replace("\n", "\\n") for t in current)
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self.window,
            "設定 Stop Tokens",
            "每行一個 stop token（可用 \\n 表示換行）:",
            display,
        )
        if ok:
            tokens = [line.replace("\\n", "\n") for line in text.splitlines() if line.strip()]
            self._chat.settings.set_stop_tokens(tokens)

    def configure_max_stop_tokens(self) -> None:
        """Configure maximum number of stop tokens sent to the API."""
        current = self._chat.settings.max_stop_tokens
        value, ok = QtWidgets.QInputDialog.getInt(
            self.window,
            "設定 Stop Tokens 上限",
            "最多送出幾個 stop tokens（0 = 無限制）:",
            current,
            0,
            100,
        )
        if ok:
            self._chat.settings.set_max_stop_tokens(value)

    def configure_api_key(self) -> None:
        """Configure chat API key."""
        current = self._chat.settings.api_key
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定 API Key",
            "API Key（留空則不送認證 header）:",
            QtWidgets.QLineEdit.EchoMode.Password,
            current,
        )
        if ok:
            self._chat.settings.set_api_key(text.strip())

    def apply_provider_preset(self, preset_name: str) -> None:
        """Apply a provider preset configuration (URL, model, endpoint only)."""
        preset = _PROVIDER_PRESETS[preset_name]
        settings = self._chat.settings
        settings.set_server_url(preset["server_url"])
        settings.set_model(preset["model"])
        settings.set_endpoint_path(preset["endpoint_path"])
        settings.set_max_stop_tokens(preset["max_stop_tokens"])

    def open_settings_dialog(self) -> None:
        """Open the unified API settings dialog."""
        if self._settings_dialog is None:
            from ..dialogs.chat_settings_dialog import ChatSettingsDialog

            self._settings_dialog = ChatSettingsDialog(self._core_manager, parent=self.window)
        else:
            # Re-read current settings — values may have changed via env / other UI.
            self._settings_dialog.refresh()

        self._settings_dialog.exec()
