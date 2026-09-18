import threading
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from doro_app.core.presence.controller import PresenceController
from doro_app.core.presence.models import PageEvent


def page(text):
    return PageEvent(1, "https://example.test", "Example", text)


def make_controller(tmp_path):
    orch = Mock()

    def present(text, *, should_present, on_present):
        if should_present():
            on_present(text)
        return text

    orch.present_character_reply.side_effect = present
    busy = [False]
    controller = PresenceController(orch, tmp_path / "presence.json", lambda: busy[0])
    controller.settings["react"] = True
    bridge = SimpleNamespace(current_page=None, shutdown=lambda: None)
    controller._bridge = bridge
    return controller, orch, bridge, busy


def test_busy_coalesces_and_reacts_once(qtbot, tmp_path):
    controller, orch, bridge, busy = make_controller(tmp_path)
    try:
        busy[0] = True
        orch.make_presence_request.return_value = lambda: "(happy) Hello"
        for text in ("first", "second"):
            bridge.current_page = page(text)
            controller._on_page(bridge.current_page)
        orch.make_presence_request.assert_not_called()
        busy[0] = False
        controller._pump()
        qtbot.waitUntil(lambda: orch.present_character_reply.call_count == 1)
        assert orch.make_presence_request.call_args.args[0].text == "second"
        controller._on_page(bridge.current_page)
        assert orch.make_presence_request.call_count == 1
    finally:
        controller.shutdown()


def test_new_page_discards_old_model_result(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    release = threading.Event()

    def old_answer():
        release.wait(2)
        return "Old answer"

    orch.make_presence_request.side_effect = [old_answer, lambda: "New answer"]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        bridge.current_page = page("new")
        controller._on_page(bridge.current_page)
        release.set()
        qtbot.waitUntil(lambda: orch.present_character_reply.call_count == 1)
        orch.present_character_reply.assert_called_once_with(
            "New answer",
            should_present=ANY,
            on_present=ANY,
        )
    finally:
        release.set()
        controller.shutdown()


def test_user_interrupt_discards_background_reply(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    release = threading.Event()
    orch.make_presence_request.return_value = lambda: (release.wait(2), "Hello")[1]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        controller.interrupt()
        release.set()
        qtbot.waitUntil(lambda: not controller._running)
        orch.present_character_reply.assert_not_called()
    finally:
        release.set()
        controller.shutdown()


def test_failure_then_new_event_recovers_and_silent_does_not_speak(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)

    def fail():
        raise RuntimeError("offline")

    orch.make_presence_request.side_effect = [fail, lambda: "[SILENT]"]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        qtbot.waitUntil(lambda: not controller._running)
        assert controller._gate.degraded
        bridge.current_page = page("new")
        controller._on_page(bridge.current_page)
        qtbot.waitUntil(lambda: not controller._running)
        assert not controller._gate.degraded
        orch.present_character_reply.assert_not_called()
    finally:
        controller.shutdown()


def test_reply_waits_for_character_to_finish_moving(qapp, tmp_path):
    controller, orch, bridge, busy = make_controller(tmp_path)
    try:
        event = page("article")
        bridge.current_page = event
        busy[0] = True
        controller._on_result(event, controller._epoch, "Hello", True)
        orch.present_character_reply.assert_not_called()
        busy[0] = False
        controller._pump()
        orch.present_character_reply.assert_called_once_with(
            "Hello",
            should_present=ANY,
            on_present=ANY,
        )
    finally:
        controller.shutdown()


@pytest.mark.parametrize(
    "change",
    [
        "unchanged",
        "interrupt",
        "page",
        "away_and_back",
        "disconnect",
        "disable",
        "shutdown",
    ],
)
def test_presence_revalidates_when_walk_finishes(qapp, tmp_path, change):
    from doro_app.core.action.dispatcher import ActionDispatcher
    from doro_app.core.chat.orchestrator import ChatOrchestrator

    state = Mock()
    state.get_current_state.return_value.key = "idle"
    # The sample reply starts with "Article ..."; a real state service returns
    # None for a non-state leading word, so it is not stripped as a state key.
    state.parse_state_from_action.return_value = None
    movement = Mock()
    movement.has_active_movement = True
    completions = []
    movement.add_completion_listener.side_effect = lambda cb: (
        completions.append(cb),
        lambda: None,
    )[1]

    def schedule(ms, cb):
        return None

    orch = ChatOrchestrator(Mock(), movement, state)
    dispatcher = ActionDispatcher(state, schedule)
    orch._action_dispatcher = dispatcher
    orch._schedule = schedule
    spoken = []
    orch.bubble_text_requested.connect(lambda text, _opts: spoken.append(text))
    controller = PresenceController(
        orch, tmp_path / "presence.json", lambda: not dispatcher.is_idle
    )
    controller.settings["react"] = True
    event = page("article")
    bridge = SimpleNamespace(current_page=event, shutdown=lambda: None)
    controller._bridge = bridge
    controller._observed_page = event
    try:
        controller._on_result(
            event, controller._epoch, "Article reply [MOVE:dir=right;distance=80]", True
        )
        assert completions and not spoken
        assert controller._last_reaction == ""
        if change == "interrupt":
            controller.interrupt()
        elif change in {"page", "away_and_back", "disconnect"}:
            bridge.current_page = None if change == "disconnect" else page("another article")
            controller._on_page(bridge.current_page)
            if change == "away_and_back":
                bridge.current_page = event
                controller._on_page(event)
        elif change == "disable":
            controller.apply_settings({"enabled": False, "react": False})
        elif change == "shutdown":
            controller.shutdown()
        completions[0]()
        expected = ["Article reply"] if change == "unchanged" else []
        assert spoken == expected
        assert controller._last_reaction == ("Article reply" if expected else "")
    finally:
        controller.shutdown()
