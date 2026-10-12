import threading
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from doro_app.core.llm import character_reply_model
from doro_app.core.presence.controller import PresenceController
from doro_app.core.presence.models import PageEvent

PresenceReply = character_reply_model(["happy"], decide_worth_saying=True)


def page(text):
    return PageEvent(1, "https://example.test", "Example", text)


def reply(line, *, worth_saying=True, move=None):
    return PresenceReply.model_validate(
        {"worth_saying": worth_saying, "state": None, "line": line, "move": move}
    )


def make_controller(tmp_path):
    orch = Mock()

    def present(answer, *, should_present, on_present):
        if should_present():
            on_present(answer.line)
        return answer.line

    orch.present_structured_reply.side_effect = present
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
        orch.make_presence_request.return_value = lambda: reply("Hello")
        for text in ("first", "second"):
            bridge.current_page = page(text)
            controller._on_page(bridge.current_page)
        orch.make_presence_request.assert_not_called()
        busy[0] = False
        controller._pump()
        qtbot.waitUntil(lambda: orch.present_structured_reply.call_count == 1)
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
        return reply("Old answer")

    new_answer = reply("New answer")
    orch.make_presence_request.side_effect = [old_answer, lambda: new_answer]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        bridge.current_page = page("new")
        controller._on_page(bridge.current_page)
        release.set()
        qtbot.waitUntil(lambda: orch.present_structured_reply.call_count == 1)
        orch.present_structured_reply.assert_called_once_with(
            new_answer,
            should_present=ANY,
            on_present=ANY,
        )
    finally:
        release.set()
        controller.shutdown()


def test_user_interrupt_discards_background_reply(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    release = threading.Event()
    orch.make_presence_request.return_value = lambda: (release.wait(2), reply("Hello"))[1]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        controller.interrupt()
        release.set()
        qtbot.waitUntil(lambda: not controller._running)
        orch.present_structured_reply.assert_not_called()
    finally:
        release.set()
        controller.shutdown()


def test_quiet_discards_inflight_and_does_not_replay_pages(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    release = threading.Event()
    orch.make_presence_request.return_value = lambda: (release.wait(2), reply("Hello"))[1]
    try:
        bridge.current_page = page("before quiet")
        controller._on_page(bridge.current_page)
        controller.set_quiet(True)
        bridge.current_page = page("during quiet")
        controller._on_page(bridge.current_page)
        release.set()
        qtbot.waitUntil(lambda: not controller._running)
        controller.set_quiet(False)
        controller._pump()
        orch.present_structured_reply.assert_not_called()
        assert orch.make_presence_request.call_count == 1
        assert controller.current_page == bridge.current_page
    finally:
        release.set()
        controller.shutdown()


def test_failure_then_new_event_recovers_and_silent_does_not_speak(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)

    def fail():
        raise RuntimeError("offline")

    orch.make_presence_request.side_effect = [fail, lambda: reply("", worth_saying=False)]
    try:
        bridge.current_page = page("old")
        controller._on_page(bridge.current_page)
        qtbot.waitUntil(lambda: not controller._running)
        assert controller._gate.degraded
        bridge.current_page = page("new")
        controller._on_page(bridge.current_page)
        qtbot.waitUntil(lambda: not controller._running)
        assert not controller._gate.degraded
        orch.present_structured_reply.assert_not_called()
    finally:
        controller.shutdown()


def test_reply_waits_for_character_to_finish_moving(qapp, tmp_path):
    controller, orch, bridge, busy = make_controller(tmp_path)
    try:
        event = page("article")
        bridge.current_page = event
        busy[0] = True
        hello = reply("Hello")
        controller._on_result(event, controller._epoch, hello, True)
        orch.present_structured_reply.assert_not_called()
        busy[0] = False
        controller._pump()
        orch.present_structured_reply.assert_called_once_with(
            hello,
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
            event,
            controller._epoch,
            reply("Article reply", move={"dir": "right", "distance": 80}),
            True,
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


def test_worth_saying_false_stays_silent_and_healthy(qapp, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    try:
        event = page("article")
        bridge.current_page = event
        controller._running = True
        controller._on_result(event, controller._epoch, reply("", worth_saying=False), True)
        orch.present_structured_reply.assert_not_called()
        assert not controller._gate.degraded
        assert controller.status == "分頁陪伴運作中"
    finally:
        controller.shutdown()


def test_unusable_reply_degrades_until_next_event(qapp, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    try:
        event = page("article")
        bridge.current_page = event
        controller._running = True
        controller._on_result(event, controller._epoch, None, False)
        orch.present_structured_reply.assert_not_called()
        assert controller._gate.degraded
    finally:
        controller.shutdown()


def test_reaction_waits_for_bubble_but_next_request_may_start(qtbot, tmp_path):
    """A visible line (idle, heartbeat) is not covered by a tab reaction."""
    controller, orch, bridge, _busy = make_controller(tmp_path)
    bubble = [True]
    controller._bubble_busy = lambda: bubble[0]
    try:
        orch.make_presence_request.return_value = lambda: reply("好看的頁面")
        bridge.current_page = page("first")
        controller._on_page(bridge.current_page)
        qtbot.waitUntil(lambda: controller._completed is not None)
        qtbot.wait(600)  # several pump ticks while the bubble is still up
        orch.present_structured_reply.assert_not_called()
        bubble[0] = False
        qtbot.waitUntil(lambda: orch.present_structured_reply.call_count == 1, timeout=2000)
    finally:
        controller.shutdown()


def test_bubble_does_not_block_starting_a_request(qtbot, tmp_path):
    controller, orch, bridge, _busy = make_controller(tmp_path)
    controller._bubble_busy = lambda: True
    try:
        orch.make_presence_request.return_value = lambda: reply("嗨")
        bridge.current_page = page("first")
        controller._on_page(bridge.current_page)
        orch.make_presence_request.assert_called_once()
    finally:
        controller.shutdown()
