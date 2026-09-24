"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore

from ...constants import (
    CHAT_DEFAULT_HISTORY_TURNS,
    CHAT_THREAD_CLEANUP_DELAY_MS,
)
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger
from ..llm.structured import SETTINGS_PREAMBLE
from .chat import build_messages_for_mistral_instruct, resolve_chat_endpoint
from .chat_rules import CHAT_RULES
from .retry import ChatRetryPolicy
from .settings import ChatSettings
from .validator import ResponseValidator

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

    def __init__(
        self, request_id: str, endpoint: str, payload: dict, timeout: int, api_key: str = ""
    ):
        super().__init__()
        self.request_id = request_id
        self.endpoint = endpoint
        self.payload = payload
        self.timeout = timeout
        self.api_key = api_key
        self.signals = ChatWorkerSignals()
        self.setAutoDelete(True)  # QThreadPool will delete this after run()

    @QtCore.Slot()
    def run(self):
        """Execute the chat request and emit result signal."""
        from .chat import perform_chat_request

        try:
            result = perform_chat_request(self.endpoint, self.payload, self.timeout, self.api_key)
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
        doro_state_provider: TextProvider | None = None,
        a11y_tree_provider: TextProvider | None = None,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        logger.debug("Initializing ChatController")

        self._config_manager = config_manager
        # prompt_path is handed to ChatSettings (which owns the prompt file);
        # the controller no longer persists it directly.
        self._state_service = state_service
        self._state_text_provider = state_text_provider
        self._movement_hint_provider = movement_hint_provider
        self._doro_state_provider: TextProvider = doro_state_provider or (lambda: "")
        self._a11y_tree_provider: TextProvider = a11y_tree_provider or (lambda: "")

        # Response validation
        self._validator = ResponseValidator(state_service)

        # User-configurable settings live in their own module (backlog #5).
        self._settings = ChatSettings(
            config_manager=config_manager,
            prompt_path=prompt_path,
            parent=self,
        )

        # Retry logic (counter, limit, original message, decision) lives in
        # its own module so it has a single home (backlog #5 stage 2).
        self._retry = ChatRetryPolicy(config_manager.chat.max_retries)
        self._history_turns = config_manager.chat.history_turns

        self._history: list[dict[str, str]] = []
        self._pool = QtCore.QThreadPool.globalInstance()
        self._current_worker: ChatWorker | None = None
        self._current_request_id: str | None = None
        self._cancelled_requests: set[str] = set()
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False

        logger.info(
            f"ChatController initialized: server={self._settings.server_url}, "
            f"model={self._settings.model}, timeout={self._settings.timeout_seconds}s"
        )

    # ------------------------------------------------------------------ Public API

    @property
    def settings(self) -> ChatSettings:
        """The chat settings store (server URL, model, prompt, …).

        Callers reach settings through this object rather than through
        pass-through getters on the controller/orchestrator.
        """
        return self._settings

    @property
    def is_inflight(self) -> bool:
        return self._inflight

    @property
    def has_history(self) -> bool:
        return bool(self._history)

    def clear_history(self):
        self._history.clear()
        self._last_user_message = ""

    def start_request(
        self,
        user_message: str,
        *,
        is_auto: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[bool, str | None]:
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

        # Seed the retry policy with the original message (no-op on retries).
        self._retry.remember_original(cleaned)

        logger.debug("Building chat payload")
        # max_tokens 覆寫：讀網頁的正式答覆需要比寵物一句話更多字數，避免講到一半被砍。
        payload = self._build_chat_payload(cleaned, max_tokens_override=max_tokens)

        self._current_request_id = QtCore.QUuid.createUuid().toString()

        logger.debug(f"Submitting chat request to thread pool (id={self._current_request_id})")
        # Use QRunnable + QThreadPool (official PySide6 pattern)
        worker = ChatWorker(
            self._current_request_id,
            endpoint,
            payload,
            int(self._settings.timeout_seconds),
            self._settings.api_key,
        )

        # Connect worker signals to handlers (QueuedConnection for thread safety)
        worker.signals.result.connect(
            self._handle_worker_result, QtCore.Qt.ConnectionType.QueuedConnection
        )
        worker.signals.error.connect(
            self._handle_worker_exception, QtCore.Qt.ConnectionType.QueuedConnection
        )
        worker.signals.finished.connect(
            self._handle_worker_finished, QtCore.Qt.ConnectionType.QueuedConnection
        )

        self._current_worker = worker
        self._pool.start(worker)
        self._inflight = True
        self._last_user_message = cleaned
        self._request_is_auto = is_auto

        retry_info = (
            f" (retry {self._retry.attempt}/{self._retry.max_retries})"
            if self._retry.attempt > 0
            else ""
        )
        logger.info(f"Starting chat request{retry_info} (auto={is_auto})")
        self.request_started.emit(cleaned, is_auto)
        return True, None

    def cancel_inflight(self):
        if not self._inflight or not self._current_request_id:
            return
        logger.info(f"Cancelling chat request id={self._current_request_id}")
        request_id = self._current_request_id  # 保存 ID，避免 reset 後變 None
        self._cancelled_requests.add(request_id)
        # Note: QRunnable cannot be cancelled once started in QThreadPool
        # We mark it as cancelled and ignore results in handlers
        self._reset_worker_state()
        self._retry.reset()  # terminal — clear retry state for next request
        self.request_cancelled.emit(request_id)  # emit 保存的 ID

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

        # A 200 response can still carry no usable text (empty content, or
        # the parser found nothing) — perform_chat_request returns
        # (None, None) then. Treat it as a failed request instead of calling
        # len() on None, which would crash this slot and leave _inflight
        # stuck until the finished-signal fallback fires.
        if not assistant_text:
            logger.warning("Worker returned empty assistant text; treating as no-response")
            self._handle_worker_error("No assistant response returned.")
            return

        logger.info(f"Worker finished successfully, response length: {len(assistant_text)}")

        # Validate response
        validation = self._validator.validate(assistant_text)

        if not validation.valid:
            logger.warning(f"Response validation failed: {validation.error_message}")

            # Ask the retry policy for the next attempt. It owns the counter,
            # the limit, and the original-message preservation — so
            # `_reset_worker_state()` below no longer needs to (and must not)
            # touch retry state. Returns None when the failure isn't
            # retryable or the max-retry gate has tripped.
            retry_message = self._retry.next_retry(validation)
            if retry_message is not None:
                logger.info(
                    f"Retrying request (attempt {self._retry.attempt}/{self._retry.max_retries})"
                )

                # Don't add failed response to history
                was_auto = self._request_is_auto
                self._reset_worker_state()

                # IMPORTANT: Delay retry to let the current worker cleanup finish
                def _delayed_retry():
                    success, error = self.start_request(retry_message, is_auto=was_auto)
                    if not success:
                        logger.error(f"Retry failed to start: {error}")
                        # Terminal: the retry never launched. Clear retry state
                        # so it doesn't leak into the next independent request
                        # (a stale counter would skip original-message seeding).
                        self._retry.reset()
                        self.request_failed.emit(
                            f"Response validation failed and retry failed: {validation.error_message}",
                            was_auto,
                        )

                # Wait for Qt thread cleanup before retrying
                QtCore.QTimer.singleShot(CHAT_THREAD_CLEANUP_DELAY_MS, _delayed_retry)
                return

            # Max retries exceeded or shouldn't retry
            logger.error(
                f"Response validation failed after {self._retry.attempt} retries: {validation.error_message}"
            )
            was_auto = self._request_is_auto
            self._reset_worker_state()
            self._retry.reset()  # terminal — clear retry state for next request

            self.request_failed.emit(
                f"Response validation failed: {validation.error_message}",
                was_auto,
            )
            return

        # Validation passed
        logger.info(
            f"Response validation passed (state={validation.has_state}, movement={validation.has_movement}, dialogue={validation.has_dialogue})"
        )

        if self._last_user_message:
            self._history.append({"role": "user", "content": self._last_user_message})
        self._history.append({"role": "assistant", "content": assistant_text})
        self._trim_history()

        was_auto = self._request_is_auto
        self._reset_worker_state()
        self._retry.reset()  # terminal — clear retry state for next request

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
        """
        Handle worker finished signal (cleanup/fallback).

        保底邏輯：如果 worker 完成了但還在 inflight（沒收到 result/error），
        視為異常並強制重置。
        """
        if request_id != self._current_request_id:
            logger.debug(f"Ignoring finished for stale request id={request_id}")
            return

        # 保底：如果還在 inflight，代表沒收到 result 或 error 信號
        if self._inflight and request_id == self._current_request_id:
            logger.warning(
                "Worker finished but still inflight (no result/error received), forcing cleanup"
            )
            was_auto = self._request_is_auto
            self._reset_worker_state()
            self._retry.reset()  # terminal — clear retry state for next request
            self.request_failed.emit("Worker completed without result", was_auto)

    @QtCore.Slot(str)
    def _handle_worker_error(self, error_message: str):
        logger.error(f"Worker error: {error_message}")

        was_auto = self._request_is_auto
        self._reset_worker_state()
        self._retry.reset()  # terminal — clear retry state for next request

        logger.debug(f"Emitting request_failed signal (auto={was_auto})")
        self.request_failed.emit(error_message, was_auto)

    def _reset_worker_state(self):
        # Worker/inflight bookkeeping only. Retry state is deliberately NOT
        # cleared here — that used to zero the counter mid-retry (before the
        # next attempt was launched), which defeated the max-retry gate and
        # dropped the original message. Terminal paths call
        # `self._retry.reset()` explicitly instead.
        logger.debug("Resetting worker state")
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False
        self._current_request_id = None
        self._current_worker = None

    # ------------------------------------------------------------------ Payload helpers

    def _build_chat_payload(
        self, user_message: str, *, max_tokens_override: int | None = None
    ) -> dict:
        messages: list[dict[str, str]] = []
        system_prompt = self._compose_system_prompt()
        stop_tokens = self._settings.stop_tokens
        max_stop_tokens = self._settings.max_stop_tokens
        if max_stop_tokens > 0:
            stop_tokens = stop_tokens[:max_stop_tokens]

        if system_prompt:
            first_entry = build_messages_for_mistral_instruct(system_prompt, user_message)
        else:
            first_entry = [{"role": "user", "content": user_message}]

        history = copy.deepcopy(self._history)
        messages.extend(history)
        messages.extend(first_entry)

        max_tokens = self._settings.max_tokens
        if max_tokens_override is not None and max_tokens_override > 0:
            # 只往上取，不會意外把使用者設定的額度調小。
            max_tokens = max(max_tokens, int(max_tokens_override))

        return {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "max_tokens": max_tokens,
            "stop": stop_tokens,
        }

    def _compose_system_prompt(self) -> str:
        # 人設（使用者可改）＋ 聊天的任務說明與格式（程式負責）。
        persona = (self._settings.system_prompt or "").strip()
        prompt = "\n\n".join(
            part for part in (SETTINGS_PREAMBLE, persona, CHAT_RULES.strip()) if part
        )
        state_list = self._safe_call_provider(self._state_text_provider)
        placeholder = "{{STATE_LIST}}"
        if placeholder in prompt:
            prompt = prompt.replace(placeholder, state_list, 1)
        elif state_list:
            prompt = f"{prompt}\n\n{state_list}" if prompt else state_list

        movement_hint = self._safe_call_provider(self._movement_hint_provider)
        if movement_hint:
            prompt = f"{prompt}\n\n{movement_hint}" if prompt else movement_hint

        doro_state = self._safe_call_provider(self._doro_state_provider)
        if doro_state:
            prompt = f"{prompt}\n\n{doro_state}" if prompt else doro_state

        a11y_tree = self._safe_call_provider(self._a11y_tree_provider)
        if a11y_tree:
            prompt = f"{prompt}\n\n{a11y_tree}" if prompt else a11y_tree
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
        return resolve_chat_endpoint(self._settings.server_url, self._settings.endpoint_path)

    def _trim_history(self, max_turns: int = CHAT_DEFAULT_HISTORY_TURNS):
        max_turns = max(
            1, self._history_turns if max_turns == CHAT_DEFAULT_HISTORY_TURNS else max_turns
        )
        max_entries = max_turns * 2
        if len(self._history) > max_entries:
            self._history = self._history[-max_entries:]
