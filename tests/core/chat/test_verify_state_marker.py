"""Tests for stripping the leading ``(狀態)`` marker off web (verify) answers.

Verify answers are shown verbatim in the bubble, so only the single leading
state slot must be removed — parentheses inside the answer body (citations like
``(USGS)`` / ``(來源1, 來源2)``) must survive.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from doro_app.core.chat.orchestrator import ChatOrchestrator


def _make_orchestrator(state_service):
    """Build a bare orchestrator with only the state service wired.

    ``_apply_leading_state_marker`` touches nothing else, so we skip the heavy
    __init__ and inject just what the method uses.
    """
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch._state_service = state_service
    return orch


def test_literal_placeholder_marker_is_stripped_without_changing_state():
    # The model echoed the literal placeholder "狀態" (not a real state key).
    state = MagicMock()
    state.parse_state_from_action.return_value = None
    orch = _make_orchestrator(state)

    out = orch._apply_leading_state_marker("(狀態) 你好哇，我是doro！")

    assert out == "你好哇，我是doro！"
    state.set_state.assert_not_called()


def test_inline_parentheses_in_body_are_preserved():
    state = MagicMock()
    state.parse_state_from_action.return_value = None
    orch = _make_orchestrator(state)

    text = "(狀態) 洪水發生在尼泊爾(USGS)指出的地方(來源1, 來源2)。"
    out = orch._apply_leading_state_marker(text)

    assert out == "洪水發生在尼泊爾(USGS)指出的地方(來源1, 來源2)。"


def test_recognised_state_key_is_applied_and_stripped():
    state = MagicMock()
    state.parse_state_from_action.return_value = "happy"
    state.is_movement_only_state.return_value = False
    current = MagicMock()
    current.key = "idle"
    state.get_current_state.return_value = current
    orch = _make_orchestrator(state)

    out = orch._apply_leading_state_marker("(開心) doro查完了～")

    assert out == "doro查完了～"
    state.set_state.assert_called_once_with("happy")


def test_movement_only_state_is_not_applied():
    state = MagicMock()
    state.parse_state_from_action.return_value = "walk_left"
    state.is_movement_only_state.return_value = True
    orch = _make_orchestrator(state)

    out = orch._apply_leading_state_marker("(走路) 內容")

    assert out == "內容"
    state.set_state.assert_not_called()


def test_text_without_leading_marker_is_unchanged():
    state = MagicMock()
    orch = _make_orchestrator(state)

    text = "沒有開頭狀態的答覆(這個括號要保留)。"
    assert orch._apply_leading_state_marker(text) == text
    state.parse_state_from_action.assert_not_called()


def test_bare_leading_state_without_parens_is_applied_and_stripped():
    # Some models (e.g. Gemini) drop the parentheses and write "stand ...".
    state = MagicMock()
    state.parse_state_from_action.return_value = "stand"
    state.is_movement_only_state.return_value = False
    current = MagicMock()
    current.key = "idle"
    state.get_current_state.return_value = current
    orch = _make_orchestrator(state)

    out = orch._apply_leading_state_marker("stand 這篇爭議很大喔")

    assert out == "這篇爭議很大喔"
    state.set_state.assert_called_once_with("stand")


def test_bare_leading_word_that_is_not_a_state_is_left_untouched():
    state = MagicMock()
    state.parse_state_from_action.return_value = None
    orch = _make_orchestrator(state)

    text = "OK 我看看這個"
    assert orch._apply_leading_state_marker(text) == text
    state.set_state.assert_not_called()


def test_full_width_leading_marker_is_stripped():
    state = MagicMock()
    state.parse_state_from_action.return_value = None
    orch = _make_orchestrator(state)

    out = orch._apply_leading_state_marker("（狀態）欸嘿，內文(inline)不變。")

    assert out == "欸嘿，內文(inline)不變。"
