"""Phase building blocks for `Action` (see dispatcher.py).

An `Action` is an ordered list of `Phase`s that the dispatcher walks
sequentially. Each phase exposes the same protocol — `start(on_done,
on_fail)` and `cancel()` — so the dispatcher does not need to know what
the phase actually does. This module ships three commonly-needed
implementations:

- `VisualPhase`: show a state's GIF for a fixed duration, then advance.
- `EffectPhase`: run a synchronous side-effect (fire click, kick off
  movement), then advance immediately.
- `WaitPhase`: subscribe to an external completion signal and advance
  when it fires; falls back to a safety timeout that surfaces as
  failure.

Tests can use any callable matching the `Phase` protocol; production
code mostly uses these three.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from ...utils.logger import get_logger

logger = get_logger(__name__)


# (ms, callback) -> None. In production wraps `QTimer.singleShot`.
ScheduleFn = Callable[[int, Callable[[], None]], None]


class Phase(Protocol):
    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None: ...

    def cancel(self) -> None: ...


class VisualPhase:
    """Set a display state and advance after `duration_ms`.

    The dispatcher itself owns capturing/restoring the pre-action state —
    this phase only switches the visible GIF for the duration of one
    phase. After the timer fires it calls `on_done`; the next phase or
    the dispatcher's restore-pre-state step decides what comes next.
    """

    def __init__(
        self,
        state_service,
        state_key: str,
        duration_ms: int,
        schedule: ScheduleFn,
    ) -> None:
        self._state_service = state_service
        self._state_key = state_key
        self._duration_ms = int(duration_ms)
        self._schedule = schedule
        self._cancelled = False
        self._fired = False

    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None:
        # Use force=True so an in-flight transition lock (e.g. set by
        # ClickAction's wind-up coordinator) does not refuse the change.
        ok = self._state_service.set_state(self._state_key, force=True)
        if not ok:
            on_fail(f"set_state({self._state_key!r}) refused")
            return

        def _expire() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            on_done()

        self._schedule(self._duration_ms, _expire)

    def cancel(self) -> None:
        self._cancelled = True


class EffectPhase:
    """Run `callback` synchronously and advance immediately.

    If `callback` raises, the failure is reported via `on_fail`.
    Cancellation is a no-op since the side effect is instantaneous —
    once started, the work is already done.
    """

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None:
        try:
            self._callback()
        except Exception as exc:  # noqa: BLE001 - bubble up to dispatcher
            logger.exception("EffectPhase callback raised")
            on_fail(f"effect raised: {exc}")
            return
        on_done()

    def cancel(self) -> None:
        # Effects run synchronously inside `start`; there's nothing in
        # flight to interrupt. Defined for the Phase protocol.
        return None


class WaitPhase:
    """Block until an external signal fires (or a safety timeout elapses).

    `subscribe(callback) -> unsubscribe` follows the same shape as
    `MovementManager.add_completion_listener` — register, get an
    unsubscribe handle, fire-once. If the signal does not arrive within
    `safety_timeout_ms` the phase reports failure with reason
    "wait-timeout"; the dispatcher's failure path then drives the
    failure GIF / restore.
    """

    def __init__(
        self,
        subscribe: Callable[[Callable[[], None]], Callable[[], None]],
        schedule: ScheduleFn,
        safety_timeout_ms: int = 30_000,
    ) -> None:
        self._subscribe = subscribe
        self._schedule = schedule
        self._safety_timeout_ms = int(safety_timeout_ms)
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._cancelled = False
        self._fired = False

    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None:
        def _signal() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            on_done()

        def _timeout() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            on_fail("wait-timeout")

        self._unsubscribe = self._subscribe(_signal)
        self._schedule(self._safety_timeout_ms, _timeout)

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._do_unsubscribe()

    def _do_unsubscribe(self) -> None:
        unsub = self._unsubscribe
        self._unsubscribe = None
        if unsub is not None:
            try:
                unsub()
            except Exception:  # pragma: no cover - unsubscribe failures are non-fatal
                logger.exception("WaitPhase unsubscribe raised")
