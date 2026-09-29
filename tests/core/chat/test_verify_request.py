"""Verify answers go through the shared structured layer (ADR 0005)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.chat.orchestrator import WEB_ANSWER_MAX_TOKENS, ChatOrchestrator
from doro_app.core.llm import character_reply_model, structured
from doro_app.core.llm.transport import Completion


@pytest.fixture(autouse=True)
def _fresh_detection():
    structured.forget_detected_modes()
    yield
    structured.forget_detected_modes()


def _orchestrator():
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch._state_service = Mock()
    orch._state_service.visible_state_keys.return_value = ["idle", "happy"]
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


def test_verify_ask_returns_multiline_reply(monkeypatch):
    payloads = _fake_server(
        monkeypatch, '{"state":"happy","line":"找到兩個：\\n・甲站\\n・乙站","move":null}'
    )

    reply = _orchestrator()._make_verify_ask()("來源資料")

    assert reply.state == "happy"
    assert reply.line == "找到兩個：\n・甲站\n・乙站"
    payload = payloads[0]
    assert payload["max_tokens"] == WEB_ANSWER_MAX_TOKENS
    content = payload["messages"][0]["content"]
    assert "【人設】doro 很可愛" in content
    assert "唯讀搜尋結果" in content and "來源資料" in content
    assert "開頭加 (狀態)" not in content


def test_verify_ask_reasks_once_then_gives_up(monkeypatch):
    payloads = _fake_server(monkeypatch, "(happy) 找到了", "還是不對")

    assert _orchestrator()._make_verify_ask()("來源資料") is None
    assert len(payloads) == 2


def test_finished_reply_object_is_acted_out(qapp):
    orch = ChatOrchestrator(Mock(), Mock(), Mock())
    orch._state_service.is_movement_only_state.return_value = False
    orch._current_web_request_id = "r1"
    spoken = []
    orch.bubble_text_requested.connect(lambda text, _opts: spoken.append(text))
    reply = character_reply_model(["happy"]).model_validate(
        {"state": "happy", "line": "查完了 (USGS)"}
    )

    orch._on_verify_finished("r1", reply)

    orch._state_service.set_state.assert_called_once_with("happy")
    assert spoken == ["查完了 (USGS)"]


def test_finished_fixed_text_is_spoken_as_is(qapp):
    orch = ChatOrchestrator(Mock(), Mock(), Mock())
    orch._state_service.parse_state_from_action.return_value = None
    orch._current_web_request_id = "r1"
    spoken = []
    orch.bubble_text_requested.connect(lambda text, _opts: spoken.append(text))

    orch._on_verify_finished("r1", "唔…doro找不到適合的來源耶。")

    assert spoken == ["唔…doro找不到適合的來源耶。"]
