"""End-to-end check: a chat reply whose tool is ``click`` routes through the
chat orchestrator → AutomationManager → FakeInputBackend.

This is the seam that ties Phase 1c together: if any one of parser,
orchestrator dispatch, or manager wiring is wrong, the click never fires.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from doro_app.core.automation.fakes import FakeAutomationWindow, FakeInputBackend
from doro_app.core.automation.manager import AutomationManager, ClickOutcome
from doro_app.core.chat.chat_reply import chat_reply_model
from doro_app.core.chat.orchestrator import ChatOrchestrator

from .conftest import ClockStub, ConfigManagerStub, ManualScheduler


def click_reply(line="嘿嘿要幫人點囉～"):
    return chat_reply_model([]).model_validate({"line": line, "tool": {"kind": "click"}})


@pytest.fixture
def stub_controller():
    """ChatController stand-in with the signals ChatOrchestrator wires to."""
    controller = MagicMock()
    controller.request_started = MagicMock()
    controller.request_started.connect = MagicMock()
    controller.request_succeeded = MagicMock()
    controller.request_succeeded.connect = MagicMock()
    controller.request_failed = MagicMock()
    controller.request_failed.connect = MagicMock()
    return controller


@pytest.fixture
def stub_movement():
    movement = MagicMock()
    movement.handle_move_bracket.return_value = False  # mouse brackets are not move
    movement.parse_movement_token.return_value = None
    movement.record_manual_report = MagicMock()
    return movement


@pytest.fixture
def stub_state_service():
    svc = MagicMock()
    svc.parse_state_from_action.return_value = None
    svc.is_movement_only_state.return_value = False
    svc.get_current_state.return_value = MagicMock(key="idle")
    return svc


@pytest.fixture
def automation_setup():
    from doro_app.core.automation.fakes import FakeA11yClicker

    backend = FakeInputBackend()
    backend.set_window_class("Firefox")
    window = FakeAutomationWindow(foot_logical=(640, 480), foot_physical=(640, 480))
    scheduler = ManualScheduler()
    clock = ClockStub()
    config = ConfigManagerStub(mouse_enabled=True, allowlist=("Firefox",))
    coord = MagicMock()
    coord.begin.return_value = True
    coord.end.return_value = True
    clicker = FakeA11yClicker(should_succeed=True)

    manager = AutomationManager(
        config_manager=config,
        window=window,
        input_backend=backend,
        transition_coordinator=coord,
        a11y_clicker=clicker,
        schedule=scheduler,
        clock=clock,
    )
    return {
        "manager": manager,
        "backend": backend,
        "clicker": clicker,
        "window": window,
        "scheduler": scheduler,
        "clock": clock,
        "config": config,
    }


def test_click_tool_routes_to_automation_manager(
    stub_controller, stub_movement, stub_state_service, automation_setup
):
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=automation_setup["manager"],
    )

    orchestrator._on_request_succeeded(click_reply(), False)

    # Wind-up was scheduled; click hasn't fired yet.
    assert automation_setup["clicker"].invoke_calls == []
    automation_setup["scheduler"].flush()

    assert automation_setup["clicker"].invoke_calls == [(640, 480)]
    # One tool per reply → exactly one click attempt.
    assert list(automation_setup["manager"].outcomes) == [ClickOutcome.FIRED]


def test_orchestrator_without_automation_drops_click_quietly(
    stub_controller, stub_movement, stub_state_service
):
    """Default install (no automation wired) must still handle the reply."""
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=None,
    )

    assert orchestrator._on_request_succeeded(click_reply("hi"), False) == "hi"


def test_click_tool_carries_no_coordinates_or_other_mouse_actions():
    """The schema only knows a plain left click; anything else is dropped."""
    model = chat_reply_model([])
    for tool in (
        {"kind": "double_click"},
        {"kind": "drag"},
        {"kind": "scroll"},
    ):
        assert model.model_validate({"line": "點", "tool": tool}).tool is None
    click = model.model_validate({"line": "點", "tool": {"kind": "click", "x": 1, "y": 1}}).tool
    assert click.model_dump(exclude_none=True) == {"kind": "click"}
