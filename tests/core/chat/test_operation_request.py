"""Web operation asks for a strict tool decision (WebStep, ADR 0005)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.llm import structured
from doro_app.core.llm.transport import Completion


@pytest.fixture(autouse=True)
def _fresh_detection():
    structured.forget_detected_modes()
    yield
    structured.forget_detected_modes()


def _orchestrator():
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
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
        )
    )
    return orch


def _fake_server(monkeypatch, *texts):
    replies = list(texts)
    payloads = []

    def request(url, payload, timeout, api_key):
        payloads.append(json.loads(json.dumps(payload)))
        return Completion(replies.pop(0), None, 200)

    monkeypatch.setattr(structured.transport, "request_completion", request)
    return payloads


def test_operation_ask_returns_validated_step(monkeypatch):
    payloads = _fake_server(monkeypatch, '{"action":"click","n":3,"line":"點這個～"}')

    decision = _orchestrator()._make_operation_ask()("頁面狀況")

    assert decision.to_action().raw == "[web:click;n=3]"
    schema = payloads[0]["response_format"]["json_schema"]
    assert schema["name"] == "WebStep"
    content = payloads[0]["messages"][0]["content"]
    assert "【人設】doro 很可愛" in content and "操作網頁瀏覽器" in content
    assert "[web:" not in content


def test_invalid_step_is_reasked_with_the_error(monkeypatch):
    payloads = _fake_server(
        monkeypatch, '{"action":"click","line":"點～"}', '{"action":"click","n":1,"line":""}'
    )

    decision = _orchestrator()._make_operation_ask()("頁面狀況")

    assert decision.n == 1
    reask = payloads[1]["messages"][-1]["content"]
    assert "click 需要 n" in reask


def test_still_invalid_after_one_reask_gives_none(monkeypatch):
    payloads = _fake_server(monkeypatch, "[web:click;n=1]", '{"action":"goto","url":"x"}')

    assert _orchestrator()._make_operation_ask()("頁面狀況") is None
    assert len(payloads) == 2
