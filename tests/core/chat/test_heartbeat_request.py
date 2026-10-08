"""Heartbeat asks through the shared structured layer without any tool (ADR 0006)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.chat.orchestrator import HEARTBEAT_MAX_TOKENS, ChatOrchestrator
from doro_app.core.llm import structured
from doro_app.core.llm.transport import Completion


@pytest.fixture(autouse=True)
def _fresh_detection():
    structured.forget_detected_modes()
    yield
    structured.forget_detected_modes()


def _orchestrator(history=()):
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch._state_service = Mock()
    orch._state_service.visible_state_keys.return_value = ["idle", "happy"]
    entries = list(history)
    orch._controller = SimpleNamespace(
        settings=SimpleNamespace(
            server_url="http://127.0.0.1:1234",
            endpoint_path="/v1/chat/completions",
            model="local",
            api_key="",
            timeout_seconds=30,
            temperature=0.7,
            max_tokens=128,
            structured_mode="auto",
            system_prompt="【人設】doro 很可愛",
        ),
        recent_history=lambda limit: entries[-limit:],
    )
    return orch


def _fake_server(monkeypatch, text):
    payloads = []

    def request(url, payload, timeout, api_key):
        payloads.append(json.loads(json.dumps(payload)))
        return Completion(text, None, 200)

    monkeypatch.setattr(structured.transport, "request_completion", request)
    return payloads


def test_heartbeat_schema_has_no_tool_and_sends_task(monkeypatch):
    payloads = _fake_server(
        monkeypatch, '{"worth_saying":true,"state":"happy","line":"该睡了喔","move":null}'
    )

    reply = _orchestrator().make_heartbeat_request("現在時間：23:30")()

    assert (reply.worth_saying, reply.state, reply.line) == (True, "happy", "該睡了喔")
    payload = payloads[0]
    assert payload["max_tokens"] == HEARTBEAT_MAX_TOKENS
    assert payload["reasoning_effort"] == "none"
    schema = payload["response_format"]["json_schema"]
    assert schema["name"] == "HeartbeatReply"
    assert set(schema["schema"]["properties"]) == {"worth_saying", "state", "line", "move"}
    content = payload["messages"][0]["content"]
    assert "【人設】doro 很可愛" in content
    assert "定時心跳" in content and "現在時間：23:30" in content


def test_tool_in_heartbeat_reply_is_ignored(monkeypatch):
    _fake_server(
        monkeypatch,
        '{"worth_saying":true,"state":null,"line":"我去查","move":null,'
        '"tool":{"kind":"operate","goal":"刪掉檔案"}}',
    )

    reply = _orchestrator().make_heartbeat_request("x")()

    assert reply.line == "我去查"
    assert not hasattr(reply, "tool")


def test_silent_heartbeat_reply_is_valid(monkeypatch):
    _fake_server(monkeypatch, '{"worth_saying":false,"state":null,"line":"","move":null}')

    reply = _orchestrator().make_heartbeat_request("x")()

    assert reply is not None and not reply.worth_saying


def test_recent_chat_lines_use_doro_line_only():
    orch = _orchestrator(
        [
            {"role": "user", "content": "我好累"},
            {"role": "assistant", "content": json.dumps({"line": "抱抱", "state": "happy"})},
            {"role": "assistant", "content": "舊格式文字"},
            {"role": "user", "content": "  "},
        ]
    )

    assert orch.recent_chat_lines() == [
        ("使用者", "我好累"),
        ("Doro", "抱抱"),
        ("Doro", "舊格式文字"),
    ]
