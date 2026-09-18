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

from collections.abc import Callable
from typing import Protocol

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
        except Exception as exc:
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
    `timeout_reason`; the dispatcher's failure path then drives the
    failure GIF / restore.

    Three optional hooks let one class cover every wait in the codebase
    (it previously spawned two near-identical copies — click's outcome
    wait and movement's completion wait):

    - ``resolve``: maps the signal *payload* to a failure reason, or
      ``None`` for success. The signal callback is invoked with whatever
      arguments ``subscribe``'s source delivers (``()`` for a bare
      completion signal, ``(outcome, detail)`` for a click outcome), and
      those arguments are forwarded to ``resolve``. Defaults to "any
      signal means success".
    - ``timeout_reason``: the string handed to ``on_fail`` when the
      safety timeout wins.
    - ``precondition``: checked once at ``start``. When it returns
      ``False`` there is nothing to wait for, so the phase short-circuits
      to success via ``schedule(0, on_done)`` rather than subscribing —
      e.g. movement kick-off that never started an animation because the
      target was already under the foot. Deferring through the scheduler
      (instead of calling ``on_done`` inline) keeps us out of the
      dispatcher's still-live phase-start frame. Note the short-circuit is
      unconditional success and does **not** consult ``resolve`` (there is
      no signal payload to map) — a "nothing happened" kick-off is a
      completed no-op, not a failure. No current caller sets both hooks.
    """

    def __init__(
        self,
        subscribe: Callable[[Callable[..., None]], Callable[[], None]],
        schedule: ScheduleFn,
        safety_timeout_ms: int = 30_000,
        *,
        resolve: Callable[..., str | None] | None = None,
        timeout_reason: str = "wait-timeout",
        precondition: Callable[[], bool] | None = None,
    ) -> None:
        self._subscribe = subscribe
        self._schedule = schedule
        self._safety_timeout_ms = int(safety_timeout_ms)
        self._resolve = resolve
        self._timeout_reason = timeout_reason
        self._precondition = precondition
        self._unsubscribe: Callable[[], None] | None = None
        self._cancelled = False
        self._fired = False

    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None:
        if self._precondition is not None and not self._precondition():
            # Nothing to wait for — complete on the next event-loop turn.
            def _instant() -> None:
                if self._cancelled or self._fired:
                    return
                self._fired = True
                on_done()

            self._schedule(0, _instant)
            return

        def _signal(*args: object) -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            reason = self._resolve(*args) if self._resolve is not None else None
            if reason is None:
                on_done()
            else:
                on_fail(reason)

        def _timeout() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            on_fail(self._timeout_reason)

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
