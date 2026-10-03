"""ask_structured: mode detection, parsing and re-asking against a fake server."""

from __future__ import annotations

import json

import pytest

from doro_app.core.llm import (
    LlmTarget,
    ask_structured,
    character_reply_model,
    compose_system,
    structured,
)
from doro_app.core.llm.transport import Completion


class FakeServer:
    """Stands in for ``transport.request_completion``; records every payload."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.payloads: list[dict] = []

    def __call__(self, url, payload, timeout, api_key):
        self.payloads.append(json.loads(json.dumps(payload)))
        reply = self.replies.pop(0)
        return reply(payload) if callable(reply) else reply


def ok(text):
    return Completion(text, None, 200)


def rejected(status=400):
    return Completion(None, f"HTTP error {status}: response_format", status)


@pytest.fixture(autouse=True)
def _fresh_detection():
    structured.forget_detected_modes()
    yield
    structured.forget_detected_modes()


def _install(monkeypatch, server):
    monkeypatch.setattr(structured.transport, "request_completion", server)
    return server


MODEL = character_reply_model(["idle", "stand"])
TARGET = LlmTarget(endpoint="http://x/v1/chat/completions", model="m")


def test_json_schema_mode_sends_inlined_schema(monkeypatch):
    server = _install(monkeypatch, FakeServer(ok('{"state":"idle","line":"嗨","move":null}')))

    result = ask_structured(TARGET, "sys", "hi", MODEL)

    assert result.value.line == "嗨"
    fmt = server.payloads[0]["response_format"]
    assert fmt["type"] == "json_schema"
    assert "$defs" not in json.dumps(fmt)
    assert "$ref" not in json.dumps(fmt)


def test_system_is_folded_into_first_user_message(monkeypatch):
    server = _install(monkeypatch, FakeServer(ok('{"line":"嗨"}')))

    ask_structured(TARGET, "SYSTEM TEXT", "hi", MODEL)

    messages = server.payloads[0]["messages"]
    assert [m["role"] for m in messages] == ["user"]
    assert messages[0]["content"].startswith("<<SYS>>\nSYSTEM TEXT")


def test_auto_falls_back_to_text_and_remembers(monkeypatch):
    server = _install(
        monkeypatch,
        FakeServer(rejected(), ok('```json\n{"line":"嗨"}\n```'), ok('{"line":"再見"}')),
    )

    first = ask_structured(TARGET, "sys", "hi", MODEL)
    second = ask_structured(TARGET, "sys", "bye", MODEL)

    assert first.value.line == "嗨"
    assert second.value.line == "再見"
    assert "response_format" in server.payloads[0]
    assert "response_format" not in server.payloads[1]
    assert "response_format" not in server.payloads[2]


def test_fallback_is_not_remembered_when_text_is_rejected_too(monkeypatch):
    server = _install(monkeypatch, FakeServer(rejected(), rejected(), ok('{"line":"嗨"}')))

    failed = ask_structured(TARGET, "sys", "hi", MODEL)
    later = ask_structured(TARGET, "sys", "hi", MODEL)

    assert failed.value is None and "400" in failed.error
    assert later.value.line == "嗨"
    assert "response_format" in server.payloads[2]


def test_explicit_text_mode_never_sends_response_format(monkeypatch):
    server = _install(monkeypatch, FakeServer(ok('好喔 {"line":"嗨"} 就這樣')))
    target = LlmTarget(endpoint=TARGET.endpoint, model="m", mode="text")

    result = ask_structured(target, "sys", "hi", MODEL)

    assert result.value.line == "嗨"
    assert "response_format" not in server.payloads[0]


def test_explicit_json_schema_mode_does_not_fall_back(monkeypatch):
    server = _install(monkeypatch, FakeServer(rejected()))
    target = LlmTarget(endpoint=TARGET.endpoint, model="m", mode="json_schema")

    result = ask_structured(target, "sys", "hi", MODEL)

    assert result.value is None
    assert len(server.payloads) == 1


def test_broken_reply_is_reasked_with_the_problem(monkeypatch):
    server = _install(monkeypatch, FakeServer(ok("idle\n嗨"), ok('{"line":"嗨"}')))

    result = ask_structured(TARGET, "sys", "hi", MODEL, retries=1)

    assert result.value.line == "嗨"
    reask = server.payloads[1]["messages"]
    assert [m["role"] for m in reask] == ["user", "assistant", "user"]
    assert reask[1]["content"] == "idle\n嗨"
    assert "找不到 JSON 物件" in reask[2]["content"]


def test_without_retries_a_broken_reply_returns_raw_and_error(monkeypatch):
    _install(monkeypatch, FakeServer(ok('{"line":""}')))

    result = ask_structured(TARGET, "sys", "hi", MODEL)

    assert result.value is None
    assert result.raw == '{"line":""}'
    assert "line" in result.error


def test_network_error_is_not_reasked(monkeypatch):
    server = _install(monkeypatch, FakeServer(Completion(None, "Network error: refused")))

    result = ask_structured(TARGET, "sys", "hi", MODEL, retries=2)

    assert result.error == "Network error: refused"
    assert len(server.payloads) == 1


def test_history_and_extra_payload_are_sent(monkeypatch):
    server = _install(monkeypatch, FakeServer(ok('{"line":"嗨"}')))
    history = [{"role": "user", "content": "早"}, {"role": "assistant", "content": "{}"}]

    ask_structured(TARGET, "sys", "hi", MODEL, history=history, extra_payload={"x": 1})

    payload = server.payloads[0]
    assert payload["messages"][:2] == history
    assert payload["x"] == 1


def test_missing_endpoint_skips_the_request(monkeypatch):
    server = _install(monkeypatch, FakeServer())

    result = ask_structured(LlmTarget(endpoint="", model="m"), "sys", "hi", MODEL)

    assert result.value is None and result.error
    assert server.payloads == []


def test_compose_system_orders_persona_task_format():
    system = compose_system("【人設】可愛", "只說一句", MODEL)

    assert system.index("【人設】") < system.index("【這次的任務】") < system.index("【回覆格式】")
    assert '"enum":["idle","stand"]' in system
