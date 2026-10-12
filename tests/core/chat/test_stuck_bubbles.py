"""A "work in progress" bubble that never auto-hides must always be replaced or cleared.

Idle liveliness, tab reactions and the heartbeat all wait while a bubble is on
screen, so a progress bubble left behind would freeze Doro until the user spoke.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.web import WebReadResult


@pytest.fixture
def orch(qapp):
    controller = Mock()
    controller.is_inflight = False
    controller.settings = SimpleNamespace(
        server_url="http://127.0.0.1:1234",
        endpoint_path="/v1/chat/completions",
        model="local",
        api_key="",
        timeout_seconds=30,
        temperature=0.7,
        max_tokens=128,
        structured_mode="auto",
        system_prompt="",
    )
    orchestrator = ChatOrchestrator(controller, Mock(), Mock(), web_runtime=Mock())
    shown = []
    orchestrator.bubble_text_requested.connect(
        lambda text, opts: shown.append((text, opts.get("auto_hide", True)))
    )
    orchestrator.bubble_clear_requested.connect(lambda: shown.append(("<clear>", None)))
    orchestrator.shown = shown
    return orchestrator


def _last_bubble_stays_forever(shown) -> bool:
    return bool(shown) and shown[-1][1] is False


def test_read_page_whose_answer_cannot_be_requested_shows_an_error(orch):
    """A: page read OK, but the chat request is refused (e.g. no server configured)."""
    orch._controller.start_request.return_value = (False, "Chat server URL is not configured.")
    orch._begin_web_read("https://example.com", "摘要")
    orch._on_web_read_result(
        orch._current_web_request_id,
        WebReadResult(url="https://example.com", title="t", text="x", error=None),
    )

    assert not _last_bubble_stays_forever(orch.shown)
    text, auto_hide = orch.shown[-1]
    assert auto_hide is True and "Chat server URL is not configured." in text


def test_failed_auto_request_clears_thinking(orch):
    """B: an automatic request shows "Thinking..." but no error bubble when it fails."""
    orch._on_request_started("auto", True)
    orch._on_request_failed("network down", True)

    assert orch.shown[-1] == ("<clear>", None)


def test_operation_that_ends_silently_clears_its_start_bubble(orch):
    """C: the operation thread stops before reporting any progress."""
    orch._config_manager = Mock()
    orch._config_manager.automation.web_operation_enabled = True
    orch._begin_operation("幫我填表")
    assert _last_bubble_stays_forever(orch.shown)

    orch._on_op_finished()

    assert orch.shown[-1] == ("<clear>", None)


@pytest.mark.parametrize("report", ["progress", "reply"])
def test_operation_that_reported_keeps_its_last_line(orch, report):
    orch._config_manager = Mock()
    orch._config_manager.automation.web_operation_enabled = True
    orch._begin_operation("幫我填表")
    if report == "progress":
        orch._on_op_progress("找到表單了")
    else:
        orch._on_op_reply("填好囉")
    before = list(orch.shown)

    orch._on_op_finished()

    assert orch.shown == before
