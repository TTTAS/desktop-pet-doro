"""`ChatSettings` — the chat settings store (backlog #5, stage 1).

Extracted from `ChatController`, which had fused two responsibilities: a
wide, shallow settings store (~12 property/setter pairs plus their
persistence) and a genuinely deep worker/retry state machine. This module
is the settings half — the values the user edits in the chat-settings
dialog, plus where they persist.

Two persistence paths, deliberately different:

- The scalar settings (server URL, model, endpoint, API key, temperature,
  timeout, stop tokens) live in QSettings via ``ConfigManager``. Writes
  are debounced through a single-shot timer so dragging a spin-box doesn't
  stall the UI with a synchronous write per keystroke.
- The system prompt is a whole document, stored in its own prompt file. It
  writes immediately on update (there's no per-keystroke editing) and never
  touches ConfigManager.

The orchestrator exposes this object directly (``orchestrator.settings``)
instead of the fourteen pass-through getters/setters it used to carry — one
deep accessor in place of a shallow forwarding layer.
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from ...constants import CHAT_CONFIG_PERSIST_DELAY_MS
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger
from ...utils.prompts import load_prompt_text, write_prompt_text

logger = get_logger(__name__)


class ChatSettings(QtCore.QObject):
    """User-configurable chat settings + their persistence.

    A QObject so it can own the debounce ``QTimer``. Construct one per
    ``ChatController``; read values through the properties and mutate them
    through the ``set_*`` methods (which schedule the debounced write).
    """

    def __init__(
        self,
        *,
        config_manager: ConfigManager,
        prompt_path: Path,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self._prompt_path = prompt_path

        chat = config_manager.chat
        self._server_url = chat.server_url
        self._model = chat.model
        self._endpoint_path = chat.endpoint_path
        self._api_key = chat.api_key
        self._timeout_seconds = chat.timeout_seconds
        self._temperature = chat.temperature
        self._stop_tokens = list(chat.stop_tokens)
        self._max_stop_tokens = chat.max_stop_tokens

        self._system_prompt = load_prompt_text(prompt_path)

        self._persist_timer = QtCore.QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(CHAT_CONFIG_PERSIST_DELAY_MS)
        self._persist_timer.timeout.connect(self._persist)

    # ------------------------------------------------------------------ Scalars

    @property
    def server_url(self) -> str:
        return self._server_url

    def set_server_url(self, url: str) -> None:
        self._server_url = url.strip()
        self._schedule_persist()

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str) -> None:
        self._model = model.strip()
        self._schedule_persist()

    @property
    def endpoint_path(self) -> str:
        return self._endpoint_path

    def set_endpoint_path(self, path: str) -> None:
        self._endpoint_path = path.strip()
        self._schedule_persist()

    @property
    def stop_tokens(self) -> list[str]:
        return list(self._stop_tokens)

    def set_stop_tokens(self, tokens: list[str]) -> None:
        self._stop_tokens = list(tokens)
        self._schedule_persist()

    @property
    def max_stop_tokens(self) -> int:
        return self._max_stop_tokens

    def set_max_stop_tokens(self, n: int) -> None:
        self._max_stop_tokens = max(n, 0)
        self._schedule_persist()

    @property
    def api_key(self) -> str:
        return self._api_key

    def set_api_key(self, key: str) -> None:
        self._api_key = key.strip()
        self._schedule_persist()

    @property
    def temperature(self) -> float:
        return float(self._temperature)

    def set_temperature(self, value: float) -> None:
        self._temperature = float(value)
        self._schedule_persist()

    @property
    def timeout_seconds(self) -> int:
        return int(self._timeout_seconds)

    def set_timeout_seconds(self, value: int) -> None:
        self._timeout_seconds = int(value)
        self._schedule_persist()

    # ------------------------------------------------------------------ System prompt

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def update_system_prompt(self, text: str) -> None:
        """Persist the system prompt to its file immediately.

        Unlike the scalar settings this is not debounced and never touches
        ConfigManager — the prompt is a document with its own file, edited
        as a whole rather than keystroke-by-keystroke.
        """
        write_prompt_text(self._prompt_path, text)
        self._system_prompt = text.strip()

    # ------------------------------------------------------------------ Persistence

    def _schedule_persist(self) -> None:
        # Debounce config writes to avoid synchronous UI stalls.
        self._persist_timer.start()

    def _persist(self) -> None:
        """Flush the scalar settings to ConfigManager. Called by the
        debounce timer (or directly in tests)."""
        self._config_manager.update_chat(
            server_url=self._server_url,
            model=self._model,
            endpoint_path=self._endpoint_path,
            api_key=self._api_key,
            temperature=self._temperature,
            timeout_seconds=self._timeout_seconds,
            stop_tokens=self._stop_tokens,
            max_stop_tokens=self._max_stop_tokens,
        )
        self._config_manager.save()
