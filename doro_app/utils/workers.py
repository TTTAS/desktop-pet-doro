"""Qt worker objects used by the Doro application."""

from __future__ import annotations

from PySide6 import QtCore

from ..core.chat.chat import perform_chat_request
from .logger import get_logger

logger = get_logger(__name__)


class ChatRequestWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, url: str, payload: dict, timeout_seconds: int):
        super().__init__()
        self._url = url
        self._payload = payload
        self._timeout_seconds = timeout_seconds
        logger.debug(f"ChatRequestWorker created for URL: {url}, timeout: {timeout_seconds}s")

    @QtCore.Slot()
    def run(self):
        logger.debug(f"ChatRequestWorker.run() started in thread: {QtCore.QThread.currentThread()}")

        try:
            assistant_text, error_message = perform_chat_request(
                self._url,
                self._payload,
                int(self._timeout_seconds),
            )

            if error_message:
                logger.error(f"ChatRequestWorker emitting error signal: {error_message}")
                self.error.emit(error_message)
                return

            if assistant_text is None:
                error_msg = "No assistant response returned."
                logger.error(f"ChatRequestWorker emitting error signal: {error_msg}")
                self.error.emit(error_msg)
                return

            logger.info(
                f"ChatRequestWorker emitting finished signal, response length: {len(assistant_text)}"
            )
            self.finished.emit(assistant_text)

        except Exception as e:
            error_msg = f"Unexpected error in ChatRequestWorker.run(): {e}"
            logger.critical(error_msg, exc_info=True)
            self.error.emit(error_msg)
