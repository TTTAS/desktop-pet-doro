"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

from PySide6 import QtCore

from .chat import build_messages_for_mistral_instruct, resolve_chat_endpoint
from .config_defaults import DEFAULT_CHAT_SERVER_URL
from .prompts import load_prompt_text, write_prompt_text
from .utils import safe_int as _safe_int
from .workers import ChatRequestWorker

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
            self._timeout_seconds = 30

        temp_value = config.value("chat/temperature", 0.7)
        try:
            self._temperature = float(temp_value)
        except (TypeError, ValueError):
            self._temperature = 0.7

        self._system_prompt = load_prompt_text(prompt_path)
        self._history: list[dict[str, str]] = []
        self._thread: QtCore.QThread | None = None
        self._worker: ChatRequestWorker | None = None
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False

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
            return False, "Message cannot be empty."
        if self._inflight:
            return False, "I am already replying, please wait a moment."

        endpoint = self._resolve_chat_endpoint()
        if not endpoint:
            return False, "Chat server URL is not configured."

        payload = self._build_chat_payload(cleaned)
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
        thread.start()
        self.request_started.emit(cleaned, is_auto)
        return True, None

    # ------------------------------------------------------------------ Worker callbacks

    @QtCore.Slot(str)
    def _handle_worker_finished(self, assistant_text: str):
        if self._last_user_message:
            self._history.append({"role": "user", "content": self._last_user_message})
        self._history.append({"role": "assistant", "content": assistant_text})
        self._trim_history()
        was_auto = self._request_is_auto
        self._reset_worker_state()
        self.request_succeeded.emit(assistant_text, was_auto)

    @QtCore.Slot(str)
    def _handle_worker_error(self, error_message: str):
        was_auto = self._request_is_auto
        self._reset_worker_state()
        self.request_failed.emit(error_message, was_auto)

    @QtCore.Slot()
    def _handle_thread_finished(self):
        self._thread = None

    def _reset_worker_state(self):
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
