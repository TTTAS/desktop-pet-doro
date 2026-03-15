"""Chat UI helper for window - handles all chat-related menu actions and dialogs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtWidgets

from ..dialogs.chat_dialog import show_chat_dialog

if TYPE_CHECKING:
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

    def __init__(self, window: DoroWindow) -> None:
        """
        Initialize ChatUIHelper.

        Args:
            window: The parent DoroWindow instance
        """
        self.window = window

    def prompt_chat(self) -> None:
        """Show chat input dialog and send message."""
        text, ok = show_chat_dialog(self.window)
        if not ok or not text.strip():
            return

        self.window.mark_user_activity()
        self.window.core_manager.send_chat_message(text.strip(), silent=False, is_auto=False)

    def clear_chat_history(self) -> None:
        """Clear chat history after confirmation."""
        reply = QtWidgets.QMessageBox.question(
            self.window,
            "清除對話紀錄",
            "確定要清除所有對話紀錄嗎？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # Use public API instead of accessing internal components
            self.window.core_manager.clear_chat_history()
            self.window.clear_bubble_text()

    def edit_chat_prompt(self) -> None:
        """Edit the chat system prompt."""
        # Use public API instead of accessing internal components
        current_prompt = self.window.core_manager.get_system_prompt()

        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self.window,
            "編輯系統提示詞",
            "系統提示詞 (System Prompt):",
            current_prompt,
        )
        if not ok:
            return

        # Use public API instead of accessing internal components
        self.window.core_manager.set_system_prompt(text)
        QtWidgets.QMessageBox.information(
            self.window,
            "提示詞已更新",
            "系統提示詞已成功更新",
        )

    def configure_chat_server(self) -> None:
        """Configure chat server URL."""
        # Use public API instead of accessing internal components
        current = self.window.core_manager.get_server_url()
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定聊天伺服器",
            "伺服器 URL:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            # Use public API instead of accessing internal components
            self.window.core_manager.set_server_url(text.strip())

    def configure_chat_model(self) -> None:
        """Configure chat model name."""
        # Use public API instead of accessing internal components
        current = self.window.core_manager.get_model_name()
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定模型",
            "模型名稱:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            # Use public API instead of accessing internal components
            self.window.core_manager.set_model_name(text.strip())

    def configure_chat_endpoint(self) -> None:
        """Configure chat API endpoint."""
        # Use public API instead of accessing internal components
        current = self.window.core_manager.get_endpoint()
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定 API 端點",
            "API 端點路徑:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            # Use public API instead of accessing internal components
            self.window.core_manager.set_endpoint(text.strip())

    def configure_chat_temperature(self) -> None:
        """Configure chat temperature parameter."""
        # Use public API instead of accessing internal components
        current = self.window.core_manager.get_temperature()
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
            # Use public API instead of accessing internal components
            self.window.core_manager.set_temperature(value)

    def configure_chat_timeout(self) -> None:
        """Configure chat request timeout."""
        current = self.window.core_manager.get_timeout()
        value, ok = QtWidgets.QInputDialog.getInt(
            self.window,
            "設定請求逾時",
            "逾時秒數:",
            current,
            1,
            300,
        )
        if ok:
            self.window.core_manager.set_timeout(value)

    def configure_stop_tokens(self) -> None:
        """Configure stop tokens (one per line)."""
        current = self.window.core_manager.get_stop_tokens()
        display = "\n".join(t.replace("\n", "\\n") for t in current)
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self.window,
            "設定 Stop Tokens",
            "每行一個 stop token（可用 \\n 表示換行）:",
            display,
        )
        if ok:
            tokens = [
                line.replace("\\n", "\n")
                for line in text.splitlines()
                if line.strip()
            ]
            self.window.core_manager.set_stop_tokens(tokens)

    def configure_max_stop_tokens(self) -> None:
        """Configure maximum number of stop tokens sent to the API."""
        current = self.window.core_manager.get_max_stop_tokens()
        value, ok = QtWidgets.QInputDialog.getInt(
            self.window,
            "設定 Stop Tokens 上限",
            "最多送出幾個 stop tokens（0 = 無限制）:",
            current,
            0,
            100,
        )
        if ok:
            self.window.core_manager.set_max_stop_tokens(value)

    def configure_api_key(self) -> None:
        """Configure chat API key."""
        current = self.window.core_manager.get_api_key()
        text, ok = QtWidgets.QInputDialog.getText(
            self.window,
            "設定 API Key",
            "API Key（留空則不送認證 header）:",
            QtWidgets.QLineEdit.EchoMode.Password,
            current,
        )
        if ok:
            self.window.core_manager.set_api_key(text.strip())

    def apply_provider_preset(self, preset_name: str) -> None:
        """Apply a provider preset configuration (URL, model, endpoint only)."""
        preset = _PROVIDER_PRESETS[preset_name]
        cm = self.window.core_manager
        cm.set_server_url(preset["server_url"])
        cm.set_model_name(preset["model"])
        cm.set_endpoint(preset["endpoint_path"])
        cm.set_max_stop_tokens(preset["max_stop_tokens"])
