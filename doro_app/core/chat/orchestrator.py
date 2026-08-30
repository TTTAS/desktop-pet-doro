"""High-level chat orchestration that glues ChatController output to the UI."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from PySide6 import QtCore

from ...utils.actions import (
    ACTION_PATTERN,
    BRACKET_PATTERN,
    parse_actions_from_text,
    extract_inline_move_commands,
)
from ...utils.paths import NETWORK_FAIL_MESSAGES_PATH
from .controller import ChatController
from ...utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from ..action import ActionDispatcher
    from ..action.phases import ScheduleFn
    from ..automation.manager import AutomationManager
    from ..movement.manager import MovementManager
    from ..state import StateService


class ChatOrchestrator(QtCore.QObject):
    """Coordinate chat requests, response parsing, and UI updates."""

    # UI notification signals (Window connects to these)
    bubble_text_requested = QtCore.Signal(str, dict)  # (text, kwargs)
    bubble_clear_requested = QtCore.Signal()
    busy_cursor_requested = QtCore.Signal(bool)  # enabled
    notification_requested = QtCore.Signal(str, str, str)  # (severity, title, message)

    def __init__(
        self,
        controller: ChatController,
        movement: MovementManager,
        state_service: StateService,
        *,
        automation: "AutomationManager | None" = None,
        action_dispatcher: "ActionDispatcher | None" = None,
        schedule: "ScheduleFn | None" = None,
    ):
        super().__init__()  # No parent
        self._controller = controller
        self._movement = movement
        self._state_service = state_service
        self._automation = automation
        self._action_dispatcher = action_dispatcher
        # Schedule is only used when building actions; tests that wire
        # `action_dispatcher` are expected to pass one too. When the
        # dispatcher is absent (legacy / unit-test path) movement and
        # click run synchronously through their managers as before.
        self._schedule = schedule

        controller.request_started.connect(self._on_request_started)
        controller.request_succeeded.connect(self._on_request_succeeded)
        controller.request_failed.connect(self._on_request_failed)

    # ------------------------------------------------------------------ Public API

    @property
    def is_inflight(self) -> bool:
        return self._controller.is_inflight

    def send_message(
        self, user_message: str, *, silent: bool = False, is_auto: bool = False
    ) -> bool:
        logger.info(f"Sending chat message (auto={is_auto}, silent={silent})")

        if self._controller.is_inflight:
            logger.warning("Chat request rejected: previous request still in flight")
            if not silent:
                self.notification_requested.emit(
                    "info",
                    "Chat",
                    "I am already replying, please wait a moment.",
                )
            return False

        started, error_message = self._controller.start_request(user_message, is_auto=is_auto)
        if not started:
            logger.error(f"Failed to start chat request: {error_message}")
            if not silent and error_message:
                self.notification_requested.emit("warning", "Chat", error_message)
            return False

        # Window handles user activity tracking before calling send_message()
        return True

    def speak_line(self, text: str) -> None:
        """Show *text* in Doro's bubble directly, without contacting the server.

        This is the no-API speech path used by autonomous idle behavior:
        the companion lines are already finished in-character dialogue, so
        there is nothing for the LLM to add. It just displays the line
        (same bubble + auto-hide the real replies get). A blank line is a
        no-op so callers don't have to guard.
        """
        stripped = (text or "").strip()
        if not stripped:
            return
        logger.info("Speaking canned line (no API)")
        self.bubble_text_requested.emit(stripped, {})

    # ------------------------------------------------------------------ Configuration API

    @property
    def settings(self):
        """The chat settings store (:class:`ChatSettings`).

        Replaces the fourteen pass-through getters/setters this class used
        to carry: callers now read/write ``orchestrator.settings.server_url``
        etc. directly on the one deep object.
        """
        return self._controller.settings

    def clear_history(self):
        """Clear the conversation history."""
        self._controller.clear_history()

    def simulate_response(self, assistant_text: str) -> str:
        """Inject text as if the chat server had returned it, for testing Doro.

        Runs the exact same handling a real reply gets — movement/state/mouse
        tags are parsed and executed and the cleaned dialogue is shown in the
        bubble — without contacting the server or touching history. Returns the
        dialogue Doro will display (empty when the reply is actions-only).
        """
        logger.info("Simulating chat response for testing")
        return self._on_request_succeeded(assistant_text or "", False)

    # ------------------------------------------------------------------ Controller callbacks

    def _on_request_started(self, _user_message: str, _is_auto: bool):
        logger.debug("Chat request started, setting busy state")
        self.bubble_text_requested.emit("Thinking...", {"auto_hide": False})
        self.busy_cursor_requested.emit(True)

    def _on_request_succeeded(self, assistant_text: str, _was_auto: bool) -> str:
        logger.info(f"Chat request succeeded, response length: {len(assistant_text)}")
        display_text = self._handle_actions_in_text(assistant_text)
        if display_text:
            self.bubble_text_requested.emit(display_text, {})
            shown = display_text
        else:
            # No dialogue survived action processing. Strip any control tokens
            # so a command-only reply (e.g. "[MOVE:dir=right]") never leaks its
            # raw tags into the bubble; if nothing readable remains, hide it.
            fallback = self._strip_control_tokens(assistant_text)
            if fallback:
                self.bubble_text_requested.emit(fallback, {"override_visibility": True})
                shown = fallback
            else:
                self.bubble_clear_requested.emit()
                shown = ""
        self.busy_cursor_requested.emit(False)
        return shown

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
        except (OSError, UnicodeDecodeError) as e:
            # OSError: File read errors (permissions, disk errors, etc.)
            # UnicodeDecodeError: Invalid UTF-8 in messages file
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
                fallback_text, {"auto_hide": True, "hide_delay_ms": 12000}
            )

    # ------------------------------------------------------------------ Response processing

    def _handle_actions_in_text(self, assistant_text: str) -> str:
        cleaned_text, actions = parse_actions_from_text(assistant_text)
        move_reports: list[str] = []
        # Mouse brackets are queued behind movement brackets in the dispatcher,
        # so the click can only fire after Doro arrives. But if the LLM emits
        # `[mouse:click]` BEFORE `[move:to;...]` in the same response, naïve
        # text-order dispatch would put click first and skip the wait entirely.
        # Defer all mouse brackets until after the loop so movement brackets
        # always reach the dispatcher first.
        from ..automation.parser import parse_mouse_bracket

        pending_mouse_tokens: list[str] = []

        for kind, token in actions:
            if kind == "bracket":
                # Phase 1c automation: `[mouse:click]` is the only accepted form.
                if parse_mouse_bracket(token) is not None:
                    # One click per response: the wind-up/Esc safety flow is
                    # designed around a single pending click, so extra
                    # `[mouse:click]` brackets in the same reply are dropped
                    # rather than queued back-to-back.
                    if pending_mouse_tokens:
                        logger.info("[automation] extra [mouse:click] in same response dropped")
                    else:
                        pending_mouse_tokens.append(token)
                    continue
                if self._dispatch_move_bracket(token, move_reports):
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
                report = self._dispatch_directional_move(direction)
                if report:
                    move_reports.append(report)

        if not cleaned_text:
            cleaned_text = assistant_text.strip()
            cleaned_text = self._strip_control_tokens(cleaned_text)

        # Scan remaining text for bare move commands not wrapped in brackets/parens
        cleaned_text, inline_dirs = extract_inline_move_commands(cleaned_text)
        for dir_str in inline_dirs:
            direction = self._movement.parse_movement_token(dir_str)
            if not direction:
                # Try with a "move" prefix so MOVE_TOKEN_PATTERN can match
                direction = self._movement.parse_movement_token(f"move {dir_str}")
            if direction:
                report = self._dispatch_directional_move(direction)
                if report:
                    move_reports.append(report)

        # All movement brackets (and bare directional commands) are now in
        # the dispatcher queue; finally enqueue the clicks behind them.
        for token in pending_mouse_tokens:
            self._handle_mouse_bracket(token)

        if move_reports:
            for report in move_reports:
                self._movement.record_manual_report(report)

        return self._clean_assistant_dialogue(cleaned_text)

    def _handle_mouse_bracket(self, token: str) -> bool:
        """Handle `[mouse:...]` brackets. Returns True if the token was claimed
        (the parser recognized it as a mouse bracket), regardless of whether
        the action was permitted. Returning True prevents downstream parsers
        from re-interpreting the same token.

        When an `ActionDispatcher` is wired (production path), the click
        is enqueued behind any in-flight movement so it cannot fire until
        Doro has arrived. Without a dispatcher (legacy / unit-test path)
        the click is started immediately — same behaviour as before.
        """
        from ..automation.parser import parse_mouse_bracket

        parse = parse_mouse_bracket(token)
        if parse is None:
            return False  # not a mouse bracket — let other parsers try

        if not parse.accepted:
            logger.warning(f"[automation] rejected mouse bracket: {parse.reason}")
            return True

        if self._automation is None:
            logger.warning(
                "[automation] [mouse:click] received but AutomationManager not "
                "built — pynput likely missing. Install with `pip install "
                "pynput` then restart Doro."
            )
            return True

        if self._action_dispatcher is not None and self._schedule is not None:
            from ..action import make_click_action

            self._action_dispatcher.dispatch(make_click_action(self._automation, self._schedule))
        else:
            self._automation.execute_click()
        return True

    def _dispatch_move_bracket(self, token: str, reports: list[str]) -> bool:
        """Run a `[move:...]` bracket either through the dispatcher or directly.

        Returns True iff the bracket was claimed (matches the legacy
        `handle_move_bracket` contract). When dispatching, we parse the
        bracket here and route a structured `MovementAction`; otherwise
        we fall back to the manager's synchronous handler.
        """
        if self._action_dispatcher is None or self._schedule is None:
            return self._movement.handle_move_bracket(token, reports)

        # Defer parsing to the manager so the manager remains the single
        # source of truth for `[move:...]` semantics. We run a dry parse
        # path: send the bracket through the manager but capture the
        # movement intent so we can re-issue it from inside a phase.
        from ..action import make_movement_action

        # Use the bracket form so the manager handles parsing + the kick-off.
        # The dispatcher's EffectPhase will re-invoke the parser; that's a
        # small double-parse cost but keeps movement parsing centralized.
        # First check the token is actually a move bracket — if not,
        # return False so the caller can try other parsers.
        from ..movement.parser import parse_move_bracket

        if parse_move_bracket(token) is None:
            return False

        self._action_dispatcher.dispatch(
            make_movement_action(
                self._movement,
                self._schedule,
                bracket_token=token,
                # Mirror the legacy synchronous path: forward bracket
                # validation reports back into the manager's history so
                # they show up in the LLM's next-turn context (otherwise
                # the LLM keeps making the same parse mistake).
                on_report=self._movement.record_manual_report,
            )
        )
        return True

    def _dispatch_directional_move(self, direction: tuple[int, int]) -> str | None:
        """Run a directional move either through the dispatcher or directly.

        Returns the move-report string (also recorded in history) for
        backwards compatibility with the existing caller logic; when
        dispatching we return None because the move runs asynchronously
        and its report is appended via the manager's own bookkeeping.
        """
        if self._action_dispatcher is None or self._schedule is None:
            return self._movement.apply_directional_move(direction)

        from ..action import make_movement_action

        self._action_dispatcher.dispatch(
            make_movement_action(self._movement, self._schedule, direction=direction)
        )
        return None

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
