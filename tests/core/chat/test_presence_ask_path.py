"""The "what's on this page?" ask path falls back to the grace page.

Tabbing to Doro to ask clears the live shared page (the browser lost focus),
so ``send_message`` must fall back to ``recent_page()`` before telling the user
it received nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import doro_app.core.chat.orchestrator as orch_mod
from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.presence.models import PageEvent


def _bare_orchestrator(presence):
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch._operating = False
    orch._web_reading = False
    orch._controller = SimpleNamespace(is_inflight=False)
    orch._presence = presence
    orch._last_user_text = ""
    orch._auto_read_used = False
    orch._pending_web_question = None
    orch._current_web_request_id = None
    return orch


def _presence(current, recent, enabled=True):
    presence = Mock()
    presence.current_page = current
    presence.recent_page.return_value = recent
    presence.settings = {"enabled": enabled}
    return presence


def _force_read_current_intent(monkeypatch):
    monkeypatch.setattr(orch_mod, "parse_web_read_command", lambda _m: None)
    monkeypatch.setattr(orch_mod, "parse_read_current_command", lambda _m: "這頁在說什麼")


def test_ask_falls_back_to_grace_page(qapp, monkeypatch):
    _force_read_current_intent(monkeypatch)
    grace = PageEvent(1, "https://ex.test", "T", "grace body")
    orch = _bare_orchestrator(_presence(current=None, recent=grace))
    captured = {}
    orch._on_web_read_result = lambda _rid, res: captured.update(text=res.text)
    spoken = []
    orch.speak_line = lambda text: spoken.append(text)

    assert orch.send_message("這頁在說什麼") is True
    assert captured["text"] == "grace body"
    assert spoken == []  # no "didn't receive a page" complaint


def test_ask_reports_when_grace_also_gone(qapp, monkeypatch):
    _force_read_current_intent(monkeypatch)
    orch = _bare_orchestrator(_presence(current=None, recent=None))
    read_calls = []
    orch._on_web_read_result = lambda _rid, res: read_calls.append(res)
    spoken = []
    orch.speak_line = lambda text: spoken.append(text)

    assert orch.send_message("這頁在說什麼") is True
    assert read_calls == []
    assert spoken and "沒有收到" in spoken[0]
