"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

from PySide6 import QtCore

from .chat import build_messages_for_mistral_instruct, resolve_chat_endpoint
from .config_defaults import DEFAULT_CHAT_SERVER_URL
from .logger import get_logger
from .prompts import load_prompt_text, write_prompt_text
from .utils import safe_int as _safe_int
from .workers import ChatRequestWorker

logger = get_logger(__name__)

TextProvider = Callable[[], str]


class ChatController(QtCore.QObject):
    """Manage chat configuration, payload building, and worker lifecycle."""

    request_started = QtCore.Signal(str, bool)
    request_succeeded = QtCore.Signal(str, bool)
    request_failed = QtCore.Signal(str, bool)

    def __init__(
        self,
        config: QtCore.QSettings,
        prompt_path: Path,
        *,
        state_text_provider: TextProvider,
        movement_hint_provider: TextProvider,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        logger.debug("Initializing ChatController")

        self._config = config
        self._prompt_path = prompt_path
        self._state_text_provider = state_text_provider
        self._movement_hint_provider = movement_hint_provider

        self._server_url = config.value("chat/server_url", DEFAULT_CHAT_SERVER_URL, str)
        self._model = config.value("chat/model", "lmstudio", str)
        self._endpoint_path = config.value("chat/endpoint_path", "/v1/chat/completions", str)

        timeout_value = config.value("chat/timeout_seconds", 30)
        try:
            self._timeout_seconds = int(timeout_value)
        except (TypeError, ValueError):
            logger.warning(f"Invalid timeout value: {timeout_value}, using default 30")
            self._timeout_seconds = 30

        temp_value = config.value("chat/temperature", 0.7)
        try:
            self._temperature = float(temp_value)
        except (TypeError, ValueError):
            logger.warning(f"Invalid temperature value: {temp_value}, using default 0.7")
            self._temperature = 0.7

        self._system_prompt = load_prompt_text(prompt_path)
        self._history: list[dict[str, str]] = []
        self._thread: QtCore.QThread | None = None
        self._worker: ChatRequestWorker | None = None
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False

        logger.info(f"ChatController initialized: server={self._server_url}, model={self._model}, timeout={self._timeout_seconds}s")

    # ------------------------------------------------------------------ Public API

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def update_system_prompt(self, text: str):
        write_prompt_text(self._prompt_path, text)
        self._system_prompt = text.strip()

    @property
    def server_url(self) -> str:
        return self._server_url

    def set_server_url(self, url: str):
        self._server_url = url.strip()
        self._persist_chat_settings()

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str):
        self._model = model.strip()
        self._persist_chat_settings()

    @property
    def endpoint_path(self) -> str:
        return self._endpoint_path

    def set_endpoint_path(self, path: str):
        self._endpoint_path = path.strip()
        self._persist_chat_settings()

    @property
    def temperature(self) -> float:
        return float(self._temperature)

    def set_temperature(self, value: float):
        self._temperature = float(value)
        self._persist_chat_settings()

    @property
    def timeout_seconds(self) -> int:
        return int(self._timeout_seconds)

    def set_timeout_seconds(self, value: int):
        self._timeout_seconds = int(value)
        self._persist_chat_settings()

    @property
    def is_inflight(self) -> bool:
        return self._inflight

    @property
    def has_history(self) -> bool:
        return bool(self._history)

    def clear_history(self):
        self._history.clear()
        self._last_user_message = ""

    def start_request(self, user_message: str, *, is_auto: bool = False) -> tuple[bool, str | None]:
        cleaned = (user_message or "").strip()
        if not cleaned:
            logger.warning("Chat request rejected: empty message")
            return False, "Message cannot be empty."

        if self._inflight:
            logger.warning("Chat request rejected: request already in flight")
            return False, "I am already replying, please wait a moment."

        endpoint = self._resolve_chat_endpoint()
        if not endpoint:
            logger.error("Chat request rejected: server URL not configured")
            return False, "Chat server URL is not configured."

        logger.debug(f"Building chat payload for message: {cleaned[:50]}...")
        payload = self._build_chat_payload(cleaned)

        logger.debug(f"Creating worker thread for endpoint: {endpoint}")
        worker = ChatRequestWorker(endpoint, payload, int(self._timeout_seconds))
        thread = QtCore.QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(self._handle_worker_error)
        worker.error.connect(thread.quit)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(self._handle_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._worker = worker
        self._thread = thread
        self._inflight = True
        self._last_user_message = cleaned
        self._request_is_auto = is_auto

        logger.info(f"Starting chat request (auto={is_auto}): {cleaned[:50]}...")
        thread.start()
        self.request_started.emit(cleaned, is_auto)
        return True, None

    # ------------------------------------------------------------------ Worker callbacks

    @QtCore.Slot(str)
    def _handle_worker_finished(self, assistant_text: str):
        logger.info(f"Worker finished successfully, response length: {len(assistant_text)}")

        if self._last_user_message:
            self._history.append({"role": "user", "content": self._last_user_message})
        self._history.append({"role": "assistant", "content": assistant_text})
        self._trim_history()

        was_auto = self._request_is_auto
        self._reset_worker_state()

        logger.debug(f"Emitting request_succeeded signal (auto={was_auto})")
        self.request_succeeded.emit(assistant_text, was_auto)

    @QtCore.Slot(str)
    def _handle_worker_error(self, error_message: str):
        logger.error(f"Worker error: {error_message}")

        was_auto = self._request_is_auto
        self._reset_worker_state()

        logger.debug(f"Emitting request_failed signal (auto={was_auto})")
        self.request_failed.emit(error_message, was_auto)

    @QtCore.Slot()
    def _handle_thread_finished(self):
        logger.debug("Worker thread finished")
        self._thread = None

    def _reset_worker_state(self):
        logger.debug("Resetting worker state")
        self._worker = None
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False

    # ------------------------------------------------------------------ Payload helpers

    def _build_chat_payload(self, user_message: str) -> dict:
        messages: list[dict[str, str]] = []
        system_prompt = self._compose_system_prompt()
        stop_tokens = ["\n人：", "\n人:", "\n你：", "\n你:", "\nUser:", "\nHuman:"]

        if system_prompt:
            first_entry = build_messages_for_mistral_instruct(system_prompt, user_message)
        else:
            first_entry = [{"role": "user", "content": user_message}]

        history = copy.deepcopy(self._history)
        messages.extend(history)
        messages.extend(first_entry)

        max_tokens = _safe_int(self._config.value("chat/max_tokens", 512), 512)

        return {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": max_tokens,
            "stop": stop_tokens,
        }

    def _compose_system_prompt(self) -> str:
        prompt = (self._system_prompt or "").strip()
        state_list = self._safe_call_provider(self._state_text_provider)
        placeholder = "{{STATE_LIST}}"
        if placeholder in prompt:
            prompt = prompt.replace(placeholder, state_list, 1)
        elif state_list:
            prompt = f"{prompt}\n\n{state_list}" if prompt else state_list

        movement_hint = self._safe_call_provider(self._movement_hint_provider)
        if movement_hint:
            prompt = f"{prompt}\n\n{movement_hint}" if prompt else movement_hint
        return prompt

    def _safe_call_provider(self, provider: TextProvider) -> str:
        try:
            value = provider() or ""
        except Exception:  # noqa: BLE001
            return ""
        return value.strip()

    def _resolve_chat_endpoint(self) -> str:
        return resolve_chat_endpoint(self._server_url, self._endpoint_path)

    def _trim_history(self, max_turns: int = 8):
        max_turns = max(1, max_turns)
        max_entries = max_turns * 2
        if len(self._history) > max_entries:
            self._history = self._history[-max_entries:]

    def _persist_chat_settings(self):
        self._config.setValue("chat/server_url", self._server_url)
        self._config.setValue("chat/model", self._model)
        self._config.setValue("chat/endpoint_path", self._endpoint_path)
        self._config.setValue("chat/temperature", float(self._temperature))
        self._config.setValue("chat/timeout_seconds", int(self._timeout_seconds))
        self._config.remove("chat/system_prompt")
        self._config.sync()
