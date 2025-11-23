"""High-level chat orchestration that glues ChatController output to the UI."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from ...utils.actions import ACTION_PATTERN, BRACKET_PATTERN, parse_actions_from_text
from ...utils.paths import NETWORK_FAIL_MESSAGES_PATH
from .controller import ChatController
from ...utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from ..movement.manager import MovementManager
    from ..state import StateService


class ChatOrchestrator(QtCore.QObject):
    """Coordinate chat requests, response parsing, and UI updates."""

    # UI notification signals (Window connects to these)
    bubble_text_requested = QtCore.Signal(str, dict)  # (text, kwargs)
    bubble_clear_requested = QtCore.Signal()
    busy_cursor_requested = QtCore.Signal(bool)  # enabled

    def __init__(self, controller: ChatController, movement: MovementManager, state_service: StateService):
        super().__init__()  # No parent
        self._controller = controller
        self._movement = movement
        self._state_service = state_service

        controller.request_started.connect(self._on_request_started)
        controller.request_succeeded.connect(self._on_request_succeeded)
        controller.request_failed.connect(self._on_request_failed)

    # ------------------------------------------------------------------ Public API

    @property
    def is_inflight(self) -> bool:
        return self._controller.is_inflight

    def send_message(self, user_message: str, *, silent: bool = False, is_auto: bool = False) -> bool:
        logger.info(f"Sending chat message (auto={is_auto}, silent={silent}): {user_message[:50]}...")

        if self._controller.is_inflight:
            logger.warning("Chat request rejected: previous request still in flight")
            if not silent:
                QtWidgets.QMessageBox.information(
                    None,  # No parent - Window handles user activity tracking
                    "Chat",
                    "I am already replying, please wait a moment.",
                )
            return False

        started, error_message = self._controller.start_request(user_message, is_auto=is_auto)
        if not started:
            logger.error(f"Failed to start chat request: {error_message}")
            if not silent and error_message:
                QtWidgets.QMessageBox.warning(None, "Chat", error_message)
            return False

        # Window handles user activity tracking before calling send_message()
        return True

    # ------------------------------------------------------------------ Configuration API (delegate to controller)

    def get_system_prompt(self) -> str:
        """Get the current system prompt."""
        return self._controller.system_prompt

    def set_system_prompt(self, text: str):
        """Update the system prompt."""
        self._controller.update_system_prompt(text)

    def get_server_url(self) -> str:
        """Get the chat server URL."""
        return self._controller.server_url

    def set_server_url(self, url: str):
        """Set the chat server URL."""
        self._controller.set_server_url(url)

    def get_model_name(self) -> str:
        """Get the model name."""
        return self._controller.model

    def set_model_name(self, model: str):
        """Set the model name."""
        self._controller.set_model(model)

    def get_endpoint(self) -> str:
        """Get the API endpoint path."""
        return self._controller.endpoint_path

    def set_endpoint(self, path: str):
        """Set the API endpoint path."""
        self._controller.set_endpoint_path(path)

    def get_temperature(self) -> float:
        """Get the temperature parameter."""
        return self._controller.temperature

    def set_temperature(self, value: float):
        """Set the temperature parameter."""
        self._controller.set_temperature(value)

    def get_timeout(self) -> int:
        """Get the request timeout in seconds."""
        return self._controller.timeout_seconds

    def set_timeout(self, seconds: int):
        """Set the request timeout in seconds."""
        self._controller.set_timeout_seconds(seconds)

    def clear_history(self):
        """Clear the conversation history."""
        self._controller.clear_history()

    # ------------------------------------------------------------------ Controller callbacks

    def _on_request_started(self, _user_message: str, _is_auto: bool):
        logger.debug("Chat request started, setting busy state")
        self.bubble_text_requested.emit("Thinking...", {"auto_hide": False})
        self.busy_cursor_requested.emit(True)

    def _on_request_succeeded(self, assistant_text: str, _was_auto: bool):
        logger.info(f"Chat request succeeded, response length: {len(assistant_text)}")
        display_text = self._handle_actions_in_text(assistant_text)
        if display_text:
            self.bubble_text_requested.emit(display_text, {})
        else:
            fallback = assistant_text.strip()
            if fallback:
                self.bubble_text_requested.emit(fallback, {"override_visibility": True})
            else:
                self.bubble_clear_requested.emit()
        self.busy_cursor_requested.emit(False)

    def _get_random_network_fail_message(self) -> str:
        """
        Get a random network failure message from network_fail_doro.txt.

        Returns:
            Random message from file, or default message if file not found
        """
        try:
            if NETWORK_FAIL_MESSAGES_PATH.exists():
                with open(NETWORK_FAIL_MESSAGES_PATH, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return random.choice(lines)
        except Exception as e:
            logger.warning(f"Failed to read network fail messages: {e}")

        # Fallback message
        return "嗚嗚……人，doro找不到回應了……"

    def _on_request_failed(self, error_message: str, was_auto: bool):
        logger.error(f"Chat request failed (auto={was_auto}): {error_message}")
        self.busy_cursor_requested.emit(False)

        # Use random network fail message from doro
        fallback_text = self._get_random_network_fail_message()

        if not was_auto:
            # FIXED: Error messages should auto-hide after longer delay (12s instead of 6s)
            # Previously used auto_hide=False which broke the timer completely
            self.bubble_text_requested.emit(
                fallback_text,
                {"auto_hide": True, "hide_delay_ms": 12000}
            )

    # ------------------------------------------------------------------ Response processing

    def _handle_actions_in_text(self, assistant_text: str) -> str:
        cleaned_text, actions = parse_actions_from_text(assistant_text)
        move_reports: list[str] = []

        for kind, token in actions:
            if kind == "bracket":
                if self._movement.handle_move_bracket(token, move_reports):
                    continue
            elif kind == "paren":
                state_key = self._state_service.parse_state_from_action(token)
                if state_key:
                    # Check if this is a movement-only state
                    is_movement_only = self._state_service.is_movement_only_state(state_key)
                    if is_movement_only:
                        self._movement.record_manual_report(
                            f"Movement state '{state_key}' 未設定方向，請更新 move_state_list。"
                        )
                        continue
                    current_state = self._state_service.get_current_state()
                    current_key = current_state.key if current_state else None
                    if state_key != current_key:
                        self._state_service.set_state(state_key)
                    continue

            direction = self._movement.parse_movement_token(token)
            if direction:
                report = self._movement.apply_directional_move(direction)
                if report:
                    move_reports.append(report)

        if not cleaned_text:
            cleaned_text = assistant_text.strip()
            cleaned_text = self._strip_control_tokens(cleaned_text)

        if move_reports:
            for report in move_reports:
                self._movement.record_manual_report(report)

        return self._clean_assistant_dialogue(cleaned_text)

    def _strip_control_tokens(self, text: str) -> str:
        stripped = (text or "").strip()
        if not stripped:
            return ""
        cleaned = ACTION_PATTERN.sub("", stripped)
        cleaned = BRACKET_PATTERN.sub("", cleaned)
        return cleaned.strip()

    def _clean_assistant_dialogue(self, text: str) -> str:
        stripped = (text or "").strip()
        if not stripped:
            return ""
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            return ""
        filtered: list[str] = []
        for line in lines:
            normalized = line.lstrip()
            ascii_line = normalized.replace("：", ":")
            lower = ascii_line.lower()
            if ascii_line.startswith("使用者說") or ascii_line.startswith("使用者:"):
                continue
            if lower.startswith("user said") or lower.startswith("user:"):
                continue
            filtered.append(line)
        target = filtered if filtered else lines
        for line in target:
            if line:
                return line
        return ""
