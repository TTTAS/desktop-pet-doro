"""End-to-end check: a `[mouse:click]` in an LLM response routes through the
chat orchestrator → AutomationManager → FakeInputBackend.

This is the seam that ties Phase 1c together: if any one of parser,
orchestrator dispatch, or manager wiring is wrong, the click never fires.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from doro_app.core.automation.fakes import FakeAutomationWindow, FakeInputBackend
from doro_app.core.automation.manager import AutomationManager, ClickOutcome
from doro_app.core.chat.orchestrator import ChatOrchestrator

from .conftest import ClockStub, ConfigManagerStub, ManualScheduler


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


def test_mouse_click_bracket_routes_to_automation_manager(
    stub_controller, stub_movement, stub_state_service, automation_setup
):
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=automation_setup["manager"],
    )

    # An assistant response with one bare `[mouse:click]` bracket.
    response = "嘿嘿要幫人點囉～[mouse:click]"
    orchestrator._handle_actions_in_text(response)

    # Wind-up was scheduled; click hasn't fired yet.
    assert automation_setup["clicker"].invoke_calls == []
    automation_setup["scheduler"].flush()

    assert automation_setup["clicker"].invoke_calls == [(640, 480)]
    assert automation_setup["manager"].outcomes[-1] == ClickOutcome.FIRED


def test_only_first_click_per_response_is_dispatched(
    stub_controller, stub_movement, stub_state_service, automation_setup
):
    """Two `[mouse:click]` brackets in one reply → one click, no BUSY churn."""
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=automation_setup["manager"],
    )

    response = "點兩下！[mouse:click] [mouse:click]"
    orchestrator._handle_actions_in_text(response)
    automation_setup["scheduler"].flush()

    assert automation_setup["clicker"].invoke_calls == [(640, 480)]
    # The second bracket was dropped before reaching the manager — exactly
    # one click attempt was recorded (no BUSY entry from a double dispatch).
    assert list(automation_setup["manager"].outcomes) == [ClickOutcome.FIRED]


def test_coordinate_form_is_rejected_silently(
    stub_controller, stub_movement, stub_state_service, automation_setup
):
    """[mouse:click;x=1;y=1] must NEVER reach the input backend."""
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=automation_setup["manager"],
    )

    response = "點這裡 [mouse:click;x=1;y=1]"
    orchestrator._handle_actions_in_text(response)
    # Even if we flush the scheduler, nothing was ever scheduled.
    automation_setup["scheduler"].flush()
    assert automation_setup["clicker"].invoke_calls == []


def test_orchestrator_without_automation_drops_bracket_quietly(
    stub_controller, stub_movement, stub_state_service
):
    """Default install (no automation wired) must still parse responses cleanly."""
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=None,
    )
    # Should not raise.
    orchestrator._handle_actions_in_text("[mouse:click] hi")


def test_unsupported_mouse_actions_never_fire(
    stub_controller, stub_movement, stub_state_service, automation_setup
):
    orchestrator = ChatOrchestrator(
        stub_controller,
        stub_movement,
        stub_state_service,
        automation=automation_setup["manager"],
    )
    for bad in ["[mouse:double_click]", "[mouse:drag;dx=10;dy=10]", "[mouse:scroll;dy=120]"]:
        orchestrator._handle_actions_in_text(bad)
    automation_setup["scheduler"].flush()
    assert automation_setup["clicker"].invoke_calls == []
