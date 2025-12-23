"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6 import QtCore

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
from ...utils.config_defaults import (
    DEFAULT_CHAT_SERVER_URL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CHAT_ENDPOINT_PATH,
    DEFAULT_CHAT_MAX_RETRIES,
)
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger
from ...utils.prompts import load_prompt_text, write_prompt_text
from ...utils.utils import safe_int as _safe_int

if TYPE_CHECKING:
    from ..state import StateService

logger = get_logger(__name__)

TextProvider = Callable[[], str]


class ChatWorkerSignals(QtCore.QObject):
    """
    Signals for ChatWorker (QRunnable).

    QRunnable cannot emit signals directly (not a QObject),
    so we use this helper QObject to hold the signals.
    """
    finished = QtCore.Signal(str)  # request_id
    result = QtCore.Signal(str, tuple)  # request_id, (assistant_text, error_message)
    error = QtCore.Signal(str, str)  # request_id, error_message


class ChatWorker(QtCore.QRunnable):
    """
    QRunnable worker for executing chat requests in QThreadPool.

    This is the official PySide6 pattern for background tasks.
    Uses signals (via ChatWorkerSignals) to return results.
    """

    def __init__(self, request_id: str, endpoint: str, payload: dict, timeout: int):
        super().__init__()
        self.request_id = request_id
        self.endpoint = endpoint
        self.payload = payload
        self.timeout = timeout
        self.signals = ChatWorkerSignals()
        self.setAutoDelete(True)  # QThreadPool will delete this after run()

    @QtCore.Slot()
    def run(self):
        """Execute the chat request and emit result signal."""
        from .chat import perform_chat_request

        try:
            result = perform_chat_request(self.endpoint, self.payload, self.timeout)
            self.signals.result.emit(self.request_id, result)
        except Exception as e:
            logger.error(f"Worker exception: {e}", exc_info=True)
            self.signals.error.emit(self.request_id, str(e))
        finally:
            self.signals.finished.emit(self.request_id)


class ChatController(QtCore.QObject):
    """Manage chat configuration, payload building, and worker lifecycle."""

    request_started = QtCore.Signal(str, bool)
    request_succeeded = QtCore.Signal(str, bool)
    request_failed = QtCore.Signal(str, bool)
    request_cancelled = QtCore.Signal(str)

    def __init__(
        self,
        prompt_path: Path,
        *,
        state_service: StateService,
        state_text_provider: TextProvider,
        movement_hint_provider: TextProvider,
        config_manager: ConfigManager,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        logger.debug("Initializing ChatController")

        self._config_manager = config_manager
        self._prompt_path = prompt_path
        self._state_service = state_service
        self._state_text_provider = state_text_provider
        self._movement_hint_provider = movement_hint_provider

        # Response validation
        self._validator = ResponseValidator(state_service)

        # Load configuration from ConfigManager
        self._max_retries = config_manager.chat.max_retries
        self._history_turns = config_manager.chat.history_turns
        self._server_url = config_manager.chat.server_url
        self._model = config_manager.chat.model
        self._endpoint_path = config_manager.chat.endpoint_path
        self._timeout_seconds = config_manager.chat.timeout_seconds
        self._temperature = config_manager.chat.temperature

        self._retry_count = 0
        self._original_user_message = ""

        self._system_prompt = load_prompt_text(prompt_path)
        self._history: list[dict[str, str]] = []
        self._pool = QtCore.QThreadPool.globalInstance()
        self._current_worker: ChatWorker | None = None
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
        # Use QRunnable + QThreadPool (official PySide6 pattern)
        worker = ChatWorker(self._current_request_id, endpoint, payload, int(self._timeout_seconds))

        # Connect worker signals to handlers
        worker.signals.result.connect(self._handle_worker_result)
        worker.signals.error.connect(self._handle_worker_exception)
        worker.signals.finished.connect(self._handle_worker_finished)

        self._current_worker = worker
        self._pool.start(worker)
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
        # Note: QRunnable cannot be cancelled once started in QThreadPool
        # We mark it as cancelled and ignore results in handlers
        self._reset_worker_state()
        self.request_cancelled.emit(self._current_request_id)

    # ------------------------------------------------------------------ Worker callbacks

    @QtCore.Slot(str, tuple)
    def _handle_worker_result(self, request_id: str, result: tuple):
        """Handle successful worker result."""
        if request_id != self._current_request_id:
            logger.debug(f"Ignoring result for stale request id={request_id}")
            return

        if request_id in self._cancelled_requests:
            logger.info(f"Request id={request_id} was cancelled; ignoring result")
            self._cancelled_requests.discard(request_id)
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

    @QtCore.Slot(str, str)
    def _handle_worker_exception(self, request_id: str, error_message: str):
        """Handle worker exception."""
        if request_id != self._current_request_id:
            logger.debug(f"Ignoring exception for stale request id={request_id}")
            return

        if request_id in self._cancelled_requests:
            logger.info(f"Request id={request_id} was cancelled; ignoring exception")
            self._cancelled_requests.discard(request_id)
            return

        self._handle_worker_error(error_message)

    @QtCore.Slot(str)
    def _handle_worker_finished(self, request_id: str):
        """Handle worker finished signal (cleanup)."""
        if request_id != self._current_request_id:
            logger.debug(f"Ignoring finished for stale request id={request_id}")
            return
        # Worker is done, cleanup happens in result/error handlers

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
        self._current_worker = None
        self._retry_count = 0
        self._original_user_message = ""

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

        if self._config_manager:
            max_tokens = self._config_manager.chat.max_tokens
        else:
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
        """
        Safely call a text provider function, returning empty string on any error.

        This method is intentionally defensive - provider functions are lambdas
        that may access external state and could fail for various reasons.
        We prefer to return empty string rather than crashing the chat system.

        Args:
            provider: Function that returns a string (e.g., state list, movement hint)

        Returns:
            Stripped string from provider, or empty string if provider fails
        """
        try:
            value = provider() or ""
        except Exception as exc:
            # Provider functions are external and can fail for many reasons:
            # - StateService not ready
            # - MovementManager in invalid state
            # - File I/O errors
            # Rather than propagate these errors and break chat, we log and continue.
            logger.warning(f"Provider function failed, using empty string: {exc}")
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
        """Save chat configuration to ConfigManager."""
        self._config_manager.update_chat(
            server_url=self._server_url,
            model=self._model,
            endpoint_path=self._endpoint_path,
            temperature=self._temperature,
            timeout_seconds=self._timeout_seconds,
        )
        self._config_manager.save()

    def _schedule_persist(self):
        # Debounce config writes to avoid synchronous UI stalls
        self._persist_timer.start()
