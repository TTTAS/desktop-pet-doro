import threading
from types import SimpleNamespace
from unittest.mock import Mock

from doro_app.core.presence.controller import PresenceController
from doro_app.core.presence.models import PageEvent


def page(text):
    return PageEvent(1, "https://example.test", "Example", text)


def make_controller(tmp_path):
    orch = Mock()
    orch.present_character_reply.side_effect = lambda text: text
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
        orch.present_character_reply.assert_called_once_with("New answer")
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
        orch.present_character_reply.assert_called_once_with("Hello")
    finally:
        controller.shutdown()
