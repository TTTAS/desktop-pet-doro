"""Presence asks through the shared structured layer (ADR 0005)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.chat.orchestrator import PRESENCE_MAX_TOKENS, ChatOrchestrator
from doro_app.core.llm import character_reply_model, structured
from doro_app.core.llm.transport import Completion
from doro_app.core.presence.models import PageEvent


@pytest.fixture(autouse=True)
def _fresh_detection():
    structured.forget_detected_modes()
    yield
    structured.forget_detected_modes()


def _orchestrator(state_keys=("idle", "happy")):
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch._state_service = Mock()
    orch._state_service.visible_state_keys.return_value = list(state_keys)
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


def _fake_server(monkeypatch, text):
    payloads = []

    def request(url, payload, timeout, api_key):
        payloads.append(json.loads(json.dumps(payload)))
        return Completion(text, None, 200)

    monkeypatch.setattr(structured.transport, "request_completion", request)
    return payloads


PAGE = PageEvent(1, "https://ex.test", "新旗艦發表", "售價一萬元")


def test_presence_request_sends_persona_task_and_schema(monkeypatch):
    payloads = _fake_server(
        monkeypatch, '{"worth_saying":true,"state":"happy","line":"好贵！","move":null}'
    )

    reply = _orchestrator().make_presence_request(PAGE, "上一句")()

    assert (reply.worth_saying, reply.state, reply.line) == (True, "happy", "好貴！")
    payload = payloads[0]
    assert payload["max_tokens"] == PRESENCE_MAX_TOKENS
    assert payload["reasoning_effort"] == "none"
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["state"]["anyOf"][0]["enum"] == ["idle", "happy"]
    content = payload["messages"][0]["content"]
    assert "【人設】doro 很可愛" in content
    assert "開口判斷" in content
    assert "售價一萬元" in content and "上一句" in content
    assert "[SILENT]" not in content


def test_presence_request_returns_none_on_broken_reply(monkeypatch):
    payloads = _fake_server(monkeypatch, "[idle] 好貴喔")

    assert _orchestrator().make_presence_request(PAGE, "")() is None
    assert len(payloads) == 1  # 不重問


def test_present_structured_reply_applies_state_then_speaks():
    orch = ChatOrchestrator(Mock(), Mock(), Mock())
    orch._state_service.is_movement_only_state.return_value = False
    orch._state_service.get_current_state.return_value.key = "idle"
    spoken = []
    orch.bubble_text_requested.connect(lambda text, _opts: spoken.append(text))
    model = character_reply_model(["idle", "happy"], decide_worth_saying=True)
    reply = model.model_validate({"worth_saying": True, "state": "happy", "line": "**哇**"})

    shown = orch.present_structured_reply(reply)

    orch._state_service.set_state.assert_called_once_with("happy")
    assert spoken == [shown] == ["哇"]
