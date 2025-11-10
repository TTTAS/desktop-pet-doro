"""Qt worker objects used by the Doro application."""

from __future__ import annotations

from PySide6 import QtCore

from .chat import perform_chat_request


class ChatRequestWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, url: str, payload: dict, timeout_seconds: int):
        super().__init__()
        self._url = url
        self._payload = payload
        self._timeout_seconds = timeout_seconds

    @QtCore.Slot()
    def run(self):
        assistant_text, error_message = perform_chat_request(
            self._url,
            self._payload,
            int(self._timeout_seconds),
        )
        if error_message:
            self.error.emit(error_message)
            return
        if assistant_text is None:
            self.error.emit("No assistant response returned.")
            return
        self.finished.emit(assistant_text)
