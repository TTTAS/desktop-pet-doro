"""Unit tests for the parameterised `WaitPhase`.

`WaitPhase` unifies what used to be three near-identical wait phases
(`WaitPhase`, click's `_AwaitClickOutcomePhase`, movement's
`_MovementWaitPhase`). The variation points are exercised directly here:

- `resolve` — maps the signal payload to a failure reason (or None = ok).
- `timeout_reason` — the string surfaced on the safety timeout.
- `precondition` — when it returns False at start, the phase short-
  circuits to success via `schedule(0, ...)` instead of subscribing.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from doro_app.core.action.phases import WaitPhase


class ManualScheduler:
    def __init__(self) -> None:
        self.scheduled: List[Tuple[int, Callable[[], None]]] = []

    def __call__(self, ms: int, fn: Callable[[], None]) -> None:
        self.scheduled.append((int(ms), fn))

    def flush(self) -> None:
        while self.scheduled:
            _, fn = self.scheduled.pop(0)
            fn()


class Signal:
    """Minimal subscribe source with an unsubscribe handle + fire helper."""

    def __init__(self) -> None:
        self.listeners: list[Callable[..., None]] = []

    def subscribe(self, cb: Callable[..., None]) -> Callable[[], None]:
        self.listeners.append(cb)

        def _unsub() -> None:
            if cb in self.listeners:
                self.listeners.remove(cb)

        return _unsub

    def fire(self, *args: object) -> None:
        for cb in list(self.listeners):
            cb(*args)


class TestDefaultBehaviour:
    def test_signal_advances_and_unsubscribes(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        fail: list[str] = []
        phase = WaitPhase(sig.subscribe, sched, safety_timeout_ms=30_000)

        phase.start(lambda: done.append(True), lambda r: fail.append(r))
        assert len(sig.listeners) == 1  # subscribed

        sig.fire()
        assert done == [True]
        assert fail == []
        assert sig.listeners == []  # unsubscribed on fire

    def test_timeout_surfaces_default_reason(self):
        sig = Signal()
        sched = ManualScheduler()
        fail: list[str] = []
        phase = WaitPhase(sig.subscribe, sched, safety_timeout_ms=30_000)

        phase.start(lambda: None, lambda r: fail.append(r))
        sched.flush()  # fire the safety timeout

        assert fail == ["wait-timeout"]
        assert sig.listeners == []


class TestResolve:
    def test_resolve_success_calls_on_done(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        fail: list[str] = []

        def resolve(outcome: str, detail: str) -> Optional[str]:
            return None if outcome == "fired" else f"{outcome}: {detail}"

        phase = WaitPhase(sig.subscribe, sched, resolve=resolve)
        phase.start(lambda: done.append(True), lambda r: fail.append(r))

        sig.fire("fired", "ok")
        assert done == [True]
        assert fail == []

    def test_resolve_failure_calls_on_fail_with_reason(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        fail: list[str] = []

        def resolve(outcome: str, detail: str) -> Optional[str]:
            return None if outcome == "fired" else f"{outcome}: {detail}"

        phase = WaitPhase(sig.subscribe, sched, resolve=resolve)
        phase.start(lambda: done.append(True), lambda r: fail.append(r))

        sig.fire("rejected-by-allowlist", "no")
        assert done == []
        assert fail == ["rejected-by-allowlist: no"]

    def test_custom_timeout_reason(self):
        sig = Signal()
        sched = ManualScheduler()
        fail: list[str] = []
        phase = WaitPhase(sig.subscribe, sched, timeout_reason="click-timeout")

        phase.start(lambda: None, lambda r: fail.append(r))
        sched.flush()

        assert fail == ["click-timeout"]


class TestPrecondition:
    def test_false_precondition_short_circuits_to_success(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        phase = WaitPhase(
            sig.subscribe, sched, precondition=lambda: False,
        )

        phase.start(lambda: done.append(True), lambda r: None)

        # Did not subscribe; queued a schedule(0, ...) instead.
        assert sig.listeners == []
        assert [ms for ms, _ in sched.scheduled] == [0]
        assert done == []  # not yet — advances on the event loop

        sched.flush()
        assert done == [True]

    def test_true_precondition_subscribes_normally(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        phase = WaitPhase(
            sig.subscribe, sched, precondition=lambda: True,
        )

        phase.start(lambda: done.append(True), lambda r: None)
        assert len(sig.listeners) == 1
        sig.fire()
        assert done == [True]


class TestCancel:
    def test_cancel_before_signal_unsubscribes_and_silences(self):
        sig = Signal()
        sched = ManualScheduler()
        done: list[bool] = []
        fail: list[str] = []
        phase = WaitPhase(sig.subscribe, sched)

        phase.start(lambda: done.append(True), lambda r: fail.append(r))
        phase.cancel()
        assert sig.listeners == []  # unsubscribed on cancel

        sched.flush()  # timeout callback must be a no-op now
        assert done == []
        assert fail == []
