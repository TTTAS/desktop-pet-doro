"""Controller encapsulating chat settings, history, and request handling."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore

from ...constants import CHAT_DEFAULT_HISTORY_TURNS
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger
from ..llm import LlmTarget, ask_structured, compose_system
from ..llm.transport import resolve_chat_endpoint
from .chat_reply import CHAT_TASK, WEB_ANSWER_TASK, chat_reply_model, web_answer_model
from .settings import ChatSettings

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
    result = QtCore.Signal(str, tuple)  # request_id, (reply, error_message)
    error = QtCore.Signal(str, str)  # request_id, error_message


class ChatWorker(QtCore.QRunnable):
    """
    QRunnable worker for executing chat requests in QThreadPool.

    This is the official PySide6 pattern for background tasks.
    Uses signals (via ChatWorkerSignals) to return results.
    """

    def __init__(self, request_id: str, ask: Callable[[], tuple]):
        super().__init__()
        self.request_id = request_id
        # Pure I/O closure built on the GUI thread; returns (reply, error_message).
        self.ask = ask
        self.signals = ChatWorkerSignals()
        self.setAutoDelete(True)  # QThreadPool will delete this after run()

    @QtCore.Slot()
    def run(self):
        """Execute the chat request and emit result signal."""
        try:
            self.signals.result.emit(self.request_id, self.ask())
        except Exception as e:
            logger.error(f"Worker exception: {e}", exc_info=True)
            self.signals.error.emit(self.request_id, str(e))
        finally:
            self.signals.finished.emit(self.request_id)


class ChatController(QtCore.QObject):
    """Manage chat configuration, payload building, and worker lifecycle."""

    request_started = QtCore.Signal(str, bool)
    request_succeeded = QtCore.Signal(object, bool)  # validated reply, was_auto
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

        # User-configurable settings live in their own module (backlog #5).
        self._settings = ChatSettings(
            config_manager=config_manager,
            prompt_path=prompt_path,
            parent=self,
        )

        # 回覆格式不合時由共用層附錯誤重問（ADR 0005）；次數沿用 max_retries 設定。
        self._max_retries = config_manager.chat.max_retries
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

    def recent_history(self, limit: int) -> list[dict[str, str]]:
        """Copy of the newest ``limit`` history entries, oldest first."""
        return [dict(entry) for entry in self._history[-limit:]] if limit > 0 else []

    def clear_history(self):
        self._history.clear()
        self._last_user_message = ""

    def start_request(
        self,
        user_message: str,
        *,
        is_auto: bool = False,
        max_tokens: int | None = None,
        web_answer: bool = False,
    ) -> tuple[bool, str | None]:
        """Start one chat request. ``web_answer`` asks for a page answer: a
        plain character reply without ``tool`` (ADR 0004)."""
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

        logger.debug("Building chat request")
        # max_tokens 覆寫：讀網頁的正式答覆需要比寵物一句話更多字數，避免講到一半被砍。
        ask = self._build_request(cleaned, max_tokens_override=max_tokens, web_answer=web_answer)

        self._current_request_id = QtCore.QUuid.createUuid().toString()

        logger.debug(f"Submitting chat request to thread pool (id={self._current_request_id})")
        # Use QRunnable + QThreadPool (official PySide6 pattern)
        worker = ChatWorker(self._current_request_id, ask)

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

        logger.info(f"Starting chat request (auto={is_auto}, web_answer={web_answer})")
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

        reply, error_message = result

        if error_message or reply is None:
            # 網路錯誤，或重問後仍不合格式（共用層已經重問過）。
            self._handle_worker_error(error_message or "No assistant response returned.")
            return

        logger.info("Chat reply validated")

        if self._last_user_message:
            self._history.append({"role": "user", "content": self._last_user_message})
        # 歷史存完整結構化回覆，讓模型看得到自己照格式回答（ADR 0005）。
        self._history.append(
            {"role": "assistant", "content": json.dumps(reply.model_dump(), ensure_ascii=False)}
        )
        self._trim_history()

        was_auto = self._request_is_auto
        self._reset_worker_state()

        logger.debug(f"Emitting request_succeeded signal (auto={was_auto})")
        self.request_succeeded.emit(reply, was_auto)

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
            self.request_failed.emit("Worker completed without result", was_auto)

    @QtCore.Slot(str)
    def _handle_worker_error(self, error_message: str):
        logger.error(f"Worker error: {error_message}")

        was_auto = self._request_is_auto
        self._reset_worker_state()

        logger.debug(f"Emitting request_failed signal (auto={was_auto})")
        self.request_failed.emit(error_message, was_auto)

    def _reset_worker_state(self):
        logger.debug("Resetting worker state")
        self._inflight = False
        self._last_user_message = ""
        self._request_is_auto = False
        self._current_request_id = None
        self._current_worker = None

    # ------------------------------------------------------------------ Payload helpers

    def _build_request(
        self,
        user_message: str,
        *,
        max_tokens_override: int | None = None,
        web_answer: bool = False,
    ) -> Callable[[], tuple]:
        """Freeze everything on the GUI thread; the returned closure only does I/O."""
        max_tokens = self._settings.max_tokens
        if max_tokens_override is not None and max_tokens_override > 0:
            # 只往上取，不會意外把使用者設定的額度調小。
            max_tokens = max(max_tokens, int(max_tokens_override))
        target = LlmTarget.from_settings(self._settings, max_tokens=max_tokens)

        state_keys = self._visible_state_keys()
        if web_answer:
            reply_model = web_answer_model(state_keys)
            system = compose_system(self._settings.system_prompt, WEB_ANSWER_TASK, reply_model)
        else:
            reply_model = chat_reply_model(state_keys)
            system = self._compose_system_prompt(reply_model)

        stop_tokens = self._settings.stop_tokens
        max_stop_tokens = self._settings.max_stop_tokens
        if max_stop_tokens > 0:
            stop_tokens = stop_tokens[:max_stop_tokens]
        history = copy.deepcopy(self._history)
        retries = self._max_retries

        def ask() -> tuple:
            result = ask_structured(
                target,
                system,
                user_message,
                reply_model,
                retries=retries,
                history=history,
                extra_payload={"stop": stop_tokens},
            )
            return result.value, result.error

        return ask

    def _compose_system_prompt(self, reply_model=None) -> str:
        """人設（使用者可改）＋ 聊天任務說明與當下情境 ＋ 回覆格式（程式負責）。"""
        if reply_model is None:
            reply_model = chat_reply_model(self._visible_state_keys())
        task = CHAT_TASK.strip()
        for provider in (
            self._state_text_provider,
            self._movement_hint_provider,
            self._doro_state_provider,
            self._a11y_tree_provider,
        ):
            block = self._safe_call_provider(provider)
            if block:
                task = f"{task}\n\n{block}"
        return compose_system(self._settings.system_prompt or "", task, reply_model)

    def _visible_state_keys(self) -> list[str]:
        try:
            return list(self._state_service.visible_state_keys())
        except Exception as exc:
            logger.warning(f"State keys unavailable, schema allows any state: {exc}")
            return []

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
