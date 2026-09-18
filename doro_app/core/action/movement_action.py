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

from collections.abc import Callable
from typing import TYPE_CHECKING

from .dispatcher import Action
from .phases import EffectPhase, ScheduleFn, WaitPhase

if TYPE_CHECKING:
    from ..movement.manager import MovementManager


# Cap on how long the dispatcher waits before deciding the movement is
# stuck (and surfacing a failure). 30s is generous — typical walks
# finish in <2s; the cap exists only to recover from genuine bugs where
# completion never signals.
MOVEMENT_SAFETY_TIMEOUT_MS = 30_000


def make_movement_action(
    movement: MovementManager,
    schedule: ScheduleFn,
    *,
    direction: tuple[int, int] | None = None,
    target: tuple[int, int] | None = None,
    bracket_token: str | None = None,
    safety_timeout_ms: int = MOVEMENT_SAFETY_TIMEOUT_MS,
    on_report: Callable[[str], None] | None = None,
) -> Action:
    """Build an Action that drives one movement to completion.

    Exactly one of `direction`, `target`, or `bracket_token` should be
    provided — they correspond to the three existing entry points on
    `MovementManager`.

    ``on_report``: optional callback the bracket path uses to surface
    validation errors (e.g. ``[移動錯誤] move:to 需要 x 與 y``). The
    orchestrator wires this to ``MovementManager.record_manual_report``
    so the LLM still sees its mistakes — without it, errors would be
    silently dropped into a throwaway list.
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
            assert bracket_token is not None
            # Collect bracket validation reports and forward them through
            # `on_report`. The orchestrator's legacy synchronous path
            # always did this; the dispatcher path used to drop them.
            local_reports: list[str] = []
            movement.handle_move_bracket(bracket_token, local_reports)
            if on_report is not None:
                for report in local_reports:
                    try:
                        on_report(report)
                    except Exception:  # pragma: no cover - listener
                        pass

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
            # `precondition` covers the no-op kick-off: `_handle_target_move`
            # returns early without an active movement when the target is
            # already under the foot, so no completion signal will ever
            # fire. Without the short-circuit the phase would block for the
            # full safety timeout and a queued click would fire 30s late at
            # the unchanged position ("Doro clicked without walking").
            WaitPhase(
                subscribe=movement.add_completion_listener,
                schedule=schedule,
                safety_timeout_ms=safety_timeout_ms,
                precondition=lambda: movement.has_active_movement,
            ),
        ],
        metadata=metadata,
    )
