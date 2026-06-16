"""ActionDispatcher — serialize action execution as state-to-state bridges.

The dispatcher is the single arbiter that decides when an action starts.
It owns three guarantees the rest of the codebase used to coordinate by
hand:

1. **One at a time.** Only the action at the head of the queue runs.
   New dispatches enqueue; they do not preempt.
2. **State as a bridge.** When an action starts, the dispatcher captures
   the current display state once. When the action finishes (whether by
   completion, failure, or cancellation) the dispatcher restores that
   captured state. Individual phases may swap the visible state during
   the action — the bridge endpoints are owned here.
3. **Differentiated failure.** On failure with a configured
   `failure_state_key`, the dispatcher briefly flips to that state
   before restoring, so users see *why* a click did not land. On
   cancellation (Esc) there is no failure GIF — the action simply
   unwinds.

The implementation is intentionally Qt-agnostic. `schedule` is a
`(ms, callback) -> None` function — production wires it to
`QTimer.singleShot`, tests inject a controllable scheduler that exposes
`run_next` / `flush`. This mirrors the pattern already used by
`AutomationManager` and the Phase classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ...utils.logger import get_logger
from .phases import Phase, ScheduleFn

logger = get_logger(__name__)


# Duration the failure GIF stays up before the dispatcher restores the
# pre-action state. 1.5s matches the click wind-up duration so failed
# and successful clicks read at the same visual weight.
DEFAULT_FAILURE_DISPLAY_MS = 1500


@dataclass
class Action:
    """Unit of work the dispatcher executes start-to-finish.

    Construction is cheap and side-effect free; phases bind to runtime
    services (state_service, MovementManager, schedule fn) and execute
    only after `ActionDispatcher.dispatch` accepts the action.
    """

    kind: str
    phases: list[Phase]
    failure_state_key: Optional[str] = None
    # Optional opaque tag callers can read off `dispatcher.current` for
    # introspection (which target a click is for, etc.). Not used by the
    # dispatcher itself.
    metadata: dict = field(default_factory=dict)


class ActionDispatcher:
    """Single-slot scheduler for `Action`s.

    Args:
        state_service: Used to capture the pre-action state and restore
            it after the action ends. Also used for the failure-state
            flip if `failure_state_key` is set.
        schedule: `(ms, callback) -> None`. Used only for the failure-GIF
            hold; phases bring their own timers.
        failure_display_ms: How long the failure GIF stays up. Defaults
            to 1.5s.
    """

    def __init__(
        self,
        state_service,
        schedule: ScheduleFn,
        failure_display_ms: int = DEFAULT_FAILURE_DISPLAY_MS,
    ) -> None:
        self._state_service = state_service
        self._schedule = schedule
        self._failure_display_ms = int(failure_display_ms)

        self._queue: list[Action] = []
        self._current: Optional[Action] = None
        self._phase_index: int = 0
        self._pre_action_state: Optional[str] = None
        # Monotonically increments every time an action starts. Captured
        # by deferred callbacks (the failure-GIF hold timer) so a stale
        # callback whose action was cancelled and replaced can detect it
        # and bail out instead of finishing the next action mid-phase.
        self._generation: int = 0

    # ------------------------------------------------------------------ Public API

    @property
    def is_idle(self) -> bool:
        return self._current is None

    @property
    def current(self) -> Optional[Action]:
        return self._current

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    def dispatch(self, action: Action) -> None:
        """Enqueue *action*. Starts immediately if the dispatcher is idle."""
        self._queue.append(action)
        if self._current is None:
            self._pop_and_start()

    def cancel_current(self, reason: str = "esc") -> None:
        """Abort the running action and clear the queue.

        Used for Esc — the user wants nothing more to happen. No failure
        GIF is shown; the pre-action state is restored and the dispatcher
        returns to idle.
        """
        if self._current is None:
            self._queue.clear()
            return

        # Cancel the current phase if any. We then short-circuit the
        # normal flow and restore directly.
        phase = self._current_phase()
        if phase is not None:
            try:
                phase.cancel()
            except Exception:  # pragma: no cover - cancel is best-effort
                logger.exception("Phase cancel raised")

        self._queue.clear()
        self._restore_and_finish()

    def clear_queue(self) -> None:
        """Drop pending actions without touching the running one."""
        self._queue.clear()

    # ------------------------------------------------------------------ Internals

    def _pop_and_start(self) -> None:
        if not self._queue:
            return
        self._current = self._queue.pop(0)
        self._phase_index = 0
        self._generation += 1

        # Capture the pre-action state once per action. This is the
        # "bridge endpoint" the dispatcher always returns to.
        current_state = self._state_service.get_current_state()
        self._pre_action_state = current_state.key if current_state else None

        logger.debug(
            "dispatcher: starting action=%s pre_state=%r phases=%d",
            self._current.kind, self._pre_action_state, len(self._current.phases),
        )
        self._run_next_phase()

    def _current_phase(self) -> Optional[Phase]:
        if self._current is None:
            return None
        if 0 <= self._phase_index < len(self._current.phases):
            return self._current.phases[self._phase_index]
        return None

    def _run_next_phase(self) -> None:
        if self._current is None:
            return
        if self._phase_index >= len(self._current.phases):
            # All phases done — successful completion path.
            self._restore_and_finish()
            return

        phase = self._current.phases[self._phase_index]
        try:
            phase.start(self._on_phase_done, self._on_phase_fail)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Phase.start raised")
            self._on_phase_fail(f"start raised: {exc}")

    def _on_phase_done(self) -> None:
        if self._current is None:
            # cancelled mid-phase — ignore late callback
            return
        self._phase_index += 1
        self._run_next_phase()

    def _on_phase_fail(self, reason: str) -> None:
        if self._current is None:
            return
        logger.info(
            "dispatcher: action=%s failed at phase=%d reason=%s",
            self._current.kind, self._phase_index, reason,
        )
        failure_key = self._current.failure_state_key
        if failure_key:
            # Flip to the failure GIF, then hold before restoring. Use
            # force=True so a still-engaged transition lock can't refuse.
            self._state_service.set_state(failure_key, force=True)
            # Capture the generation so a `cancel_current` followed by a
            # new dispatch during this hold doesn't let the stale timer
            # finish the *next* action mid-phase.
            gen = self._generation
            self._schedule(self._failure_display_ms, lambda: self._finish_failure_hold(gen))
        else:
            self._restore_and_finish()

    def _finish_failure_hold(self, generation: int) -> None:
        if generation != self._generation:
            # The action we were holding the failure GIF for has been
            # cancelled (or cancelled and replaced). Stale timer — ignore.
            return
        self._restore_and_finish()

    def _restore_and_finish(self) -> None:
        if self._current is None:
            return

        if self._pre_action_state is not None:
            current_state = self._state_service.get_current_state()
            current_key = current_state.key if current_state else None
            # Only set if different — keeps the call idempotent and
            # avoids spurious transition triggers when the action's last
            # phase already restored (e.g. MovementManager's internal
            # state restore on movement completion).
            if current_key != self._pre_action_state:
                self._state_service.set_state(self._pre_action_state, force=True)

        logger.debug("dispatcher: finished action=%s", self._current.kind)
        self._current = None
        self._phase_index = 0
        self._pre_action_state = None

        # Pump the queue.
        if self._queue:
            self._pop_and_start()
