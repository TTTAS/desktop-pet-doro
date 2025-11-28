"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6 import QtConcurrent, QtCore

from .chat import build_messages_for_mistral_instruct, resolve_chat_endpoint
from .validator import ResponseValidator
from ...constants import (
    CHAT_DEFAULT_HISTORY_TURNS,
    CHAT_DEFAULT_TIMEOUT_SECONDS,
    CHAT_DEFAULT_TEMPERATURE,
    CHAT_DEFAULT_MAX_TOKENS,
    CHAT_CONFIG_PERSIST_DELAY_MS,
    CHAT_THREAD_CLEANUP_DELAY_MS,
)
from ...utils.config_defaults import DEFAULT_CHAT_SERVER_URL
from ...utils.logger import get_logger
from ...utils.prompts import load_prompt_text, write_prompt_text
from ...utils.utils import safe_int as _safe_int

if TYPE_CHECKING:
    from ..state import StateService

logger = get_logger(__name__)

TextProvider = Callable[[], str]


class ChatController(QtCore.QObject):
    """Manage chat configuration, payload building, and worker lifecycle."""

    request_started = QtCore.Signal(str, bool)
    request_succeeded = QtCore.Signal(str, bool)
    request_failed = QtCore.Signal(str, bool)
    request_cancelled = QtCore.Signal(str)

    def __init__(
        self,
        config: QtCore.QSettings,
        prompt_path: Path,
        *,
        state_service: StateService,
        state_text_provider: TextProvider,
        movement_hint_provider: TextProvider,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        logger.debug("Initializing ChatController")

        self._config = config
        self._prompt_path = prompt_path
        self._state_service = state_service
        self._state_text_provider = state_text_provider
        self._movement_hint_provider = movement_hint_provider

        # Response validation
        self._validator = ResponseValidator(state_service)
        self._max_retries = _safe_int(config.value("chat/max_retries", 2), 2)
        self._retry_count = 0
        self._original_user_message = ""

        self._history_turns = _safe_int(
            config.value("chat/history_turns", CHAT_DEFAULT_HISTORY_TURNS),
            CHAT_DEFAULT_HISTORY_TURNS,
        )

        self._server_url = config.value("chat/server_url", DEFAULT_CHAT_SERVER_URL, str)
        self._model = config.value("chat/model", "lmstudio", str)
        self._endpoint_path = config.value("chat/endpoint_path", "/v1/chat/completions", str)

        timeout_value = config.value("chat/timeout_seconds", CHAT_DEFAULT_TIMEOUT_SECONDS)
        try:
            self._timeout_seconds = int(timeout_value)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid timeout value: {timeout_value}, "
                f"using default {CHAT_DEFAULT_TIMEOUT_SECONDS}"
            )
            self._timeout_seconds = CHAT_DEFAULT_TIMEOUT_SECONDS

        temp_value = config.value("chat/temperature", CHAT_DEFAULT_TEMPERATURE)
        try:
            self._temperature = float(temp_value)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid temperature value: {temp_value}, "
                f"using default {CHAT_DEFAULT_TEMPERATURE}"
            )
            self._temperature = CHAT_DEFAULT_TEMPERATURE

        self._system_prompt = load_prompt_text(prompt_path)
        self._history: list[dict[str, str]] = []
        self._pool = QtCore.QThreadPool.globalInstance()
        self._future: QtCore.QFuture | None = None
        self._watcher: QtCore.QFutureWatcher | None = None
        self._current_request_id: str | None = None
        self._cancelled_requests: set[str] = set()
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False

        self._persist_timer = QtCore.QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(CHAT_CONFIG_PERSIST_DELAY_MS)
        self._persist_timer.timeout.connect(self._persist_chat_settings)

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
        self._schedule_persist()

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str):
        self._model = model.strip()
        self._schedule_persist()

    @property
    def endpoint_path(self) -> str:
        return self._endpoint_path

    def set_endpoint_path(self, path: str):
        self._endpoint_path = path.strip()
        self._schedule_persist()

    @property
    def temperature(self) -> float:
        return float(self._temperature)

    def set_temperature(self, value: float):
        self._temperature = float(value)
        self._schedule_persist()

    @property
    def timeout_seconds(self) -> int:
        return int(self._timeout_seconds)

    def set_timeout_seconds(self, value: int):
        self._timeout_seconds = int(value)
        self._schedule_persist()

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

        # Save original message for potential retries (only on first request, not retries)
        if self._retry_count == 0:
            self._original_user_message = cleaned

        logger.debug(f"Building chat payload for message: {cleaned[:50]}...")
        payload = self._build_chat_payload(cleaned)

        self._current_request_id = QtCore.QUuid.createUuid().toString()

        logger.debug(f"Submitting chat request to thread pool (id={self._current_request_id})")
        future = QtConcurrent.run(
            self._pool,
            perform_chat_request,
            endpoint,
            payload,
            int(self._timeout_seconds),
        )
        watcher = QtCore.QFutureWatcher()
        watcher.setFuture(future)
        watcher.finished.connect(lambda: self._handle_future_finished(self._current_request_id))
        watcher.canceled.connect(lambda: self._handle_future_cancelled(self._current_request_id))

        self._future = future
        self._watcher = watcher
        self._inflight = True
        self._last_user_message = cleaned
        self._request_is_auto = is_auto

        retry_info = f" (retry {self._retry_count}/{self._max_retries})" if self._retry_count > 0 else ""
        logger.info(f"Starting chat request{retry_info} (auto={is_auto}): {cleaned[:50]}...")
        self.request_started.emit(cleaned, is_auto)
        return True, None

    def cancel_inflight(self):
        if not self._inflight or not self._current_request_id:
            return
        logger.info(f"Cancelling chat request id={self._current_request_id}")
        self._cancelled_requests.add(self._current_request_id)
        if self._future and self._future.isRunning():
            self._future.cancel()
        self._reset_worker_state()
        self.request_cancelled.emit(self._current_request_id)

    @QtCore.Slot()
    def _handle_future_cancelled(self, request_id: str | None):
        if request_id and request_id in self._cancelled_requests:
            logger.info(f"Future cancelled for request id={request_id}")
            self._cancelled_requests.discard(request_id)
        self._reset_worker_state()

    # ------------------------------------------------------------------ Worker callbacks

    @QtCore.Slot()
    def _handle_future_finished(self, request_id: str | None):
        if not request_id or request_id != self._current_request_id:
            logger.debug(f"Ignoring finished signal for stale request id={request_id}")
            return

        if request_id in self._cancelled_requests:
            logger.info(f"Request id={request_id} was cancelled; ignoring result")
            self._cancelled_requests.discard(request_id)
            self._reset_worker_state()
            return

        try:
            result = self._future.result() if self._future else (None, "No future result")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Future raised exception: {exc}", exc_info=True)
            self._handle_worker_error(str(exc))
            return

        assistant_text, error_message = result
        if error_message:
            self._handle_worker_error(error_message)
            return

        logger.info(f"Worker finished successfully, response length: {len(assistant_text)}")

        # Validate response
        validation = self._validator.validate(assistant_text)

        if not validation.valid:
            logger.warning(f"Response validation failed: {validation.error_message}")

            # Check if we should retry
            if self._validator.should_retry(validation) and self._retry_count < self._max_retries:
                self._retry_count += 1
                logger.info(f"Retrying request (attempt {self._retry_count}/{self._max_retries})")

                # Don't add failed response to history
                was_auto = self._request_is_auto
                self._reset_worker_state()

                # Build retry prompt
                retry_message = self._validator.build_retry_prompt(validation, self._original_user_message)

                # IMPORTANT: Delay retry to let the current worker cleanup finish
                def _delayed_retry():
                    success, error = self.start_request(retry_message, is_auto=was_auto)
                    if not success:
                        logger.error(f"Retry failed to start: {error}")
                        self.request_failed.emit(
                            f"Response validation failed and retry failed: {validation.error_message}",
                            was_auto,
                        )

                # Wait for Qt thread cleanup before retrying
                QtCore.QTimer.singleShot(CHAT_THREAD_CLEANUP_DELAY_MS, _delayed_retry)
                return

            # Max retries exceeded or shouldn't retry
            logger.error(f"Response validation failed after {self._retry_count} retries: {validation.error_message}")
            was_auto = self._request_is_auto
            self._reset_worker_state()
            self._retry_count = 0  # Reset for next request
            self._original_user_message = ""

            self.request_failed.emit(
                f"Response validation failed: {validation.error_message}",
                was_auto,
            )
            return

        # Validation passed
        logger.info(f"Response validation passed (state={validation.has_state}, movement={validation.has_movement}, dialogue={validation.has_dialogue})")

        if self._last_user_message:
            self._history.append({"role": "user", "content": self._last_user_message})
        self._history.append({"role": "assistant", "content": assistant_text})
        self._trim_history()

        was_auto = self._request_is_auto
        self._reset_worker_state()
        self._retry_count = 0  # Reset for next request
        self._original_user_message = ""

        logger.debug(f"Emitting request_succeeded signal (auto={was_auto})")
        self.request_succeeded.emit(assistant_text, was_auto)

    @QtCore.Slot(str)
    def _handle_worker_error(self, error_message: str):
        logger.error(f"Worker error: {error_message}")

        was_auto = self._request_is_auto
        self._reset_worker_state()
        self._retry_count = 0  # Reset for next request
        self._original_user_message = ""

        logger.debug(f"Emitting request_failed signal (auto={was_auto})")
        self.request_failed.emit(error_message, was_auto)

    def _reset_worker_state(self):
        logger.debug("Resetting worker state")
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False
        self._current_request_id = None
        self._future = None
        self._retry_count = 0
        self._original_user_message = ""
        if self._watcher:
            self._watcher.deleteLater()
            self._watcher = None

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

        max_tokens = _safe_int(
            self._config.value("chat/max_tokens", CHAT_DEFAULT_MAX_TOKENS),
            CHAT_DEFAULT_MAX_TOKENS,
        )

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

    def _trim_history(self, max_turns: int = CHAT_DEFAULT_HISTORY_TURNS):
        max_turns = max(1, self._history_turns if max_turns == CHAT_DEFAULT_HISTORY_TURNS else max_turns)
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

    def _schedule_persist(self):
        # Debounce config writes to avoid synchronous UI stalls
        self._persist_timer.start()
