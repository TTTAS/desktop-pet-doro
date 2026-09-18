"""Fixtures for automation tests.

The AutomationManager takes its scheduler as a constructor argument so tests
can avoid spinning a Qt event loop. `ManualScheduler` records the scheduled
callbacks and lets the test fire them in order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from doro_app.core.automation.fakes import (
    FakeA11yClicker,
    FakeAutomationWindow,
    FakeInputBackend,
)
from doro_app.core.automation.manager import AutomationManager


class ManualScheduler:
    """Records (delay_ms, callback) and runs them on demand."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[int, Callable[[], None]]] = []

    def __call__(self, ms: int, fn: Callable[[], None]) -> None:
        self.scheduled.append((int(ms), fn))

    def flush(self) -> None:
        """Run all queued callbacks in FIFO order. Callbacks may enqueue more,
        which will also be drained until the queue is empty.
        """
        while self.scheduled:
            _, fn = self.scheduled.pop(0)
            fn()

    def run_next(self) -> None:
        """Run only the head callback (useful for inspecting intermediate state)."""
        assert self.scheduled, "no callback scheduled"
        _, fn = self.scheduled.pop(0)
        fn()


@dataclass
class _AutomationConfigStub:
    mouse_enabled: bool = True
    mouse_target_allowlist: tuple = ("Firefox", "Chromium", "Chrome", "Navigator")


class ConfigManagerStub:
    """Minimal stand-in for ConfigManager: only the .automation API + update."""

    def __init__(self, *, mouse_enabled: bool = True, allowlist=("Firefox",)):
        self._automation = _AutomationConfigStub(
            mouse_enabled=mouse_enabled,
            mouse_target_allowlist=tuple(allowlist),
        )
        self.save_called = 0

    @property
    def automation(self):
        return self._automation

    def update_automation(self, **kwargs):
        if "mouse_enabled" in kwargs:
            self._automation = _AutomationConfigStub(
                mouse_enabled=bool(kwargs["mouse_enabled"]),
                mouse_target_allowlist=self._automation.mouse_target_allowlist,
            )
        if "mouse_target_allowlist" in kwargs:
            self._automation = _AutomationConfigStub(
                mouse_enabled=self._automation.mouse_enabled,
                mouse_target_allowlist=tuple(kwargs["mouse_target_allowlist"]),
            )

    def save(self):
        self.save_called += 1


class ClockStub:
    """Manually-advanced monotonic clock."""

    def __init__(self, start: float = 1000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@pytest.fixture
def fake_backend() -> FakeInputBackend:
    return FakeInputBackend()


@pytest.fixture
def fake_clicker() -> FakeA11yClicker:
    """Default: pretends the UIA InvokePattern fired successfully. Tests
    that want to exercise the NOT_INVOCABLE path build their own
    ``FakeA11yClicker(should_succeed=False)`` instead."""
    return FakeA11yClicker(should_succeed=True)


@pytest.fixture
def fake_window() -> FakeAutomationWindow:
    return FakeAutomationWindow(foot_logical=(500, 500), foot_physical=(500, 500))


@pytest.fixture
def scheduler() -> ManualScheduler:
    return ManualScheduler()


@pytest.fixture
def clock() -> ClockStub:
    return ClockStub()


@pytest.fixture
def config_stub() -> ConfigManagerStub:
    return ConfigManagerStub(mouse_enabled=True, allowlist=("Firefox",))


@pytest.fixture
def coord_stub():
    coord = MagicMock()
    coord.begin.return_value = True
    coord.end.return_value = True
    return coord


class RecordingWindUpAnimator:
    """Records begin/end calls for the wind_up_animator port."""

    def __init__(self) -> None:
        self.begin_calls: int = 0
        self.end_calls: int = 0
        self.raise_on_begin: bool = False
        self.raise_on_end: bool = False

    def begin(self) -> None:
        self.begin_calls += 1
        if self.raise_on_begin:
            raise RuntimeError("animator begin failed")

    def end(self) -> None:
        self.end_calls += 1
        if self.raise_on_end:
            raise RuntimeError("animator end failed")


@pytest.fixture
def wind_up_animator() -> RecordingWindUpAnimator:
    return RecordingWindUpAnimator()


class RecordingWarningOverlay:
    """Records begin/end calls for the warning_overlay port."""

    def __init__(self) -> None:
        self.begin_calls: list = []  # list of bounds args
        self.end_calls: int = 0
        self.raise_on_begin: bool = False
        self.raise_on_end: bool = False

    def begin(self, bounds_physical) -> None:
        self.begin_calls.append(bounds_physical)
        if self.raise_on_begin:
            raise RuntimeError("overlay begin failed")

    def end(self) -> None:
        self.end_calls += 1
        if self.raise_on_end:
            raise RuntimeError("overlay end failed")


@pytest.fixture
def warning_overlay() -> RecordingWarningOverlay:
    return RecordingWarningOverlay()


@pytest.fixture
def manager(
    config_stub: ConfigManagerStub,
    fake_window: FakeAutomationWindow,
    fake_backend: FakeInputBackend,
    fake_clicker: FakeA11yClicker,
    coord_stub,
    scheduler: ManualScheduler,
    clock: ClockStub,
) -> AutomationManager:
    return AutomationManager(
        config_manager=config_stub,
        window=fake_window,
        input_backend=fake_backend,
        transition_coordinator=coord_stub,
        a11y_clicker=fake_clicker,
        schedule=scheduler,
        clock=clock,
    )
