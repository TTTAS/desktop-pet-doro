"""High-level chat orchestration that glues ChatController output to the UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from .actions import ACTION_PATTERN, BRACKET_PATTERN, parse_actions_from_text
from .chat_controller import ChatController

if TYPE_CHECKING:
    from .movement_manager import MovementManager
    from .window import DoroWindow


class ChatOrchestrator(QtCore.QObject):
    """Coordinate chat requests, response parsing, and UI updates."""

    def __init__(self, window: DoroWindow, controller: ChatController, movement: MovementManager):
        super().__init__(window)
        self._window = window
        self._controller = controller
        self._movement = movement

        controller.request_started.connect(self._on_request_started)
        controller.request_succeeded.connect(self._on_request_succeeded)
        controller.request_failed.connect(self._on_request_failed)

    # ------------------------------------------------------------------ Public API

    @property
    def is_inflight(self) -> bool:
        return self._controller.is_inflight

    def send_message(self, user_message: str, *, silent: bool = False, is_auto: bool = False) -> bool:
        if self._controller.is_inflight:
            if not silent:
                QtWidgets.QMessageBox.information(
                    self._window,
                    "Chat",
                    "I am already replying, please wait a moment.",
                )
            return False
        started, error_message = self._controller.start_request(user_message, is_auto=is_auto)
        if not started:
            if not silent and error_message:
                QtWidgets.QMessageBox.warning(self._window, "Chat", error_message)
            return False
        self._window.mark_user_activity()
        return True

    # ------------------------------------------------------------------ Controller callbacks

    def _on_request_started(self, _user_message: str, _is_auto: bool):
        self._window.show_chat_message("Thinking...", auto_hide=False)
        self._window.set_busy_cursor(True)

    def _on_request_succeeded(self, assistant_text: str, _was_auto: bool):
        display_text = self._handle_actions_in_text(assistant_text)
        if display_text:
            self._window.show_chat_message(display_text)
        else:
            fallback = assistant_text.strip()
            if fallback:
                self._window.show_chat_message(fallback, override_visibility=True)
            else:
                self._window.clear_chat_message()
        self._window.set_busy_cursor(False)

    def _on_request_failed(self, error_message: str, was_auto: bool):
        if not was_auto:
            QtWidgets.QMessageBox.warning(
                self._window,
                "Chat",
                error_message or "Failed to reach the chat server.",
            )
        self._window.set_busy_cursor(False)
        fallback_text = (
            error_message.strip()
            if error_message and error_message.strip()
            else "I could not reach the chat server."
        )
        if not was_auto:
            self._window.show_chat_message(fallback_text, auto_hide=False)

    # ------------------------------------------------------------------ Response processing

    def _handle_actions_in_text(self, assistant_text: str) -> str:
        cleaned_text, actions = parse_actions_from_text(assistant_text)
        move_reports: list[str] = []

        for kind, token in actions:
            if kind == "bracket":
                if self._movement.handle_move_bracket(token, move_reports):
                    continue
            elif kind == "paren":
                state_key = self._window.find_state_for_action(token)
                if state_key:
                    action_kind, directions = self._window.state_manager.action_profile_for_state(state_key)
                    if action_kind == "movement" and not directions:
                        self._movement.record_manual_report(
                            f"Movement state '{state_key}' 未設定方向，請更新 move_state_list。"
                        )
                        continue
                    if state_key != self._window.current_state_key:
                        self._window.set_state(state_key)
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
