"""Dialogs for configuring chat-related preferences."""

from __future__ import annotations

from PySide6 import QtWidgets

from ..chat_controller import ChatController


class ChatSettingsDialog:
    """Encapsulate chat configuration prompts shown from the context menu."""

    def __init__(self, parent: QtWidgets.QWidget, controller: ChatController):
        self._parent = parent
        self._controller = controller

    def configure_server(self) -> None:
        current = self._controller.server_url or ""
        text, ok = QtWidgets.QInputDialog.getText(
            self._parent,
            "Chat server URL",
            "Base server URL (e.g. http://127.0.0.1:1234):",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        new_url = text.strip()
        if not new_url:
            QtWidgets.QMessageBox.warning(self._parent, "Chat server URL", "URL cannot be empty.")
            return
        self._controller.set_server_url(new_url)

    def configure_model(self) -> None:
        current = self._controller.model or ""
        text, ok = QtWidgets.QInputDialog.getText(
            self._parent,
            "Chat model name",
            "Model identifier:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        cleaned = text.strip()
        if not cleaned:
            QtWidgets.QMessageBox.warning(self._parent, "Chat model name", "Model name cannot be empty.")
            return
        self._controller.set_model(cleaned)

    def configure_endpoint(self) -> None:
        current = self._controller.endpoint_path or "/v1/chat/completions"
        text, ok = QtWidgets.QInputDialog.getText(
            self._parent,
            "Chat endpoint path",
            "Endpoint path on the server:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        cleaned = text.strip()
        if not cleaned:
            QtWidgets.QMessageBox.warning(self._parent, "Chat endpoint path", "Endpoint path cannot be empty.")
            return
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        self._controller.set_endpoint_path(cleaned)

    def configure_temperature(self) -> None:
        value, ok = QtWidgets.QInputDialog.getDouble(
            self._parent,
            "Chat temperature",
            "Sampling temperature:",
            float(self._controller.temperature),
            0.0,
            2.0,
            decimals=2,
        )
        if not ok:
            return
        self._controller.set_temperature(value)

    def configure_timeout(self) -> None:
        value, ok = QtWidgets.QInputDialog.getInt(
            self._parent,
            "Chat timeout",
            "Request timeout in seconds:",
            int(self._controller.timeout_seconds),
            5,
            120,
        )
        if not ok:
            return
        self._controller.set_timeout_seconds(value)
