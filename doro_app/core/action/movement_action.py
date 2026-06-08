"""Factory for `MovementAction` — wraps MovementManager as an Action.

`MovementManager` runs its own dt-driven physics and already manages
the walking GIF state internally (via `_set_movement_state` /
`_movement_previous_state`). The action wrapper does *not* re-introduce
those concerns; it just kicks the manager off and waits for the
completion signal we wired up alongside this refactor.

This lives in a small factory rather than a class because there is no
per-action state to carry — all the work happens inside the phases.
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from .dispatcher import Action
from .phases import EffectPhase, ScheduleFn

if TYPE_CHECKING:
    from ..movement.manager import MovementManager


# Cap on how long the dispatcher waits before deciding the movement is
# stuck (and surfacing a failure). 30s is generous — typical walks
# finish in <2s; the cap exists only to recover from genuine bugs where
# completion never signals.
MOVEMENT_SAFETY_TIMEOUT_MS = 30_000


class _MovementWaitPhase:
    """WaitPhase variant that no-ops when kick-off didn't actually start a
    movement.

    `_handle_target_move` returns early without setting `_active_movement`
    when the target is already within `completion_threshold` of Doro's
    foot — there's nothing to animate. The generic `WaitPhase` would
    subscribe to `add_completion_listener` and then block for the full
    safety timeout (30s) because no `_finish_movement` ever fires.
    Worse, the click queued behind would fire 30s late at the unchanged
    position, looking like 'Doro clicked without walking'.

    This phase checks `has_active_movement` at start time and short-
    circuits via `schedule(0, on_done)` when kick-off was a no-op,
    handing the queue off to the next action immediately.
    """

    def __init__(
        self,
        movement: "MovementManager",
        schedule: ScheduleFn,
        safety_timeout_ms: int,
    ) -> None:
        self._movement = movement
        self._schedule = schedule
        self._safety_timeout_ms = int(safety_timeout_ms)
        self._cancelled = False
        self._fired = False
        self._unsubscribe: Optional[Callable[[], None]] = None

    def start(
        self,
        on_done: Callable[[], None],
        on_fail: Callable[[str], None],
    ) -> None:
        if not self._movement.has_active_movement:
            # Schedule via the event loop rather than calling on_done
            # synchronously: we're still inside the dispatcher's phase-
            # start frame, and reentering would advance the action while
            # the dispatcher's call stack still references the current
            # phase.
            def _instant() -> None:
                if self._cancelled or self._fired:
                    return
                self._fired = True
                on_done()

            self._schedule(0, _instant)
            return

        def _signal() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._unsubscribe_safe()
            on_done()

        def _timeout() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._unsubscribe_safe()
            on_fail("wait-timeout")

        self._unsubscribe = self._movement.add_completion_listener(_signal)
        self._schedule(self._safety_timeout_ms, _timeout)

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._unsubscribe_safe()

    def _unsubscribe_safe(self) -> None:
        unsub, self._unsubscribe = self._unsubscribe, None
        if unsub is not None:
            try:
                unsub()
            except Exception:  # pragma: no cover - non-fatal
                pass


def make_movement_action(
    movement: "MovementManager",
    schedule: ScheduleFn,
    *,
    direction: Optional[tuple[int, int]] = None,
    target: Optional[tuple[int, int]] = None,
    bracket_token: Optional[str] = None,
    safety_timeout_ms: int = MOVEMENT_SAFETY_TIMEOUT_MS,
) -> Action:
    """Build an Action that drives one movement to completion.

    Exactly one of `direction`, `target`, or `bracket_token` should be
    provided — they correspond to the three existing entry points on
    `MovementManager`.
    """
    if sum(x is not None for x in (direction, target, bracket_token)) != 1:
        raise ValueError(
            "make_movement_action requires exactly one of direction / target / bracket_token"
        )

    def _kick_off() -> None:
        if direction is not None:
            movement.apply_directional_move(direction)
        elif target is not None:
            movement.apply_target_move(target[0], target[1])
        else:
            # Mirror the chat orchestrator's call: pass a fresh reports
            # list — the manager's own history already captured them.
            assert bracket_token is not None
            movement.handle_move_bracket(bracket_token, [])

    metadata: dict = {}
    if direction is not None:
        metadata["direction"] = direction
    if target is not None:
        metadata["target"] = target
    if bracket_token is not None:
        metadata["bracket"] = bracket_token

    return Action(
        kind="movement",
        # failure_state_key=None — a stuck movement is a bug, not a
        # user-visible event worth a dedicated GIF. The dispatcher will
        # simply restore the pre-action state.
        failure_state_key=None,
        phases=[
            EffectPhase(_kick_off),
            _MovementWaitPhase(movement, schedule, safety_timeout_ms),
        ],
        metadata=metadata,
    )
