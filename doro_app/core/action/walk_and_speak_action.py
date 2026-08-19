"""Factory for the autonomous "walk (then maybe speak)" idle action.

Doro takes a *visible, animated* walk in some direction and, once she
arrives, optionally says a line. Two properties make this work:

- The walk uses `MovementManager.apply_directional_walk`, the physics
  animation — not the instant one-step `apply_directional_move`. So the
  wander is actually seen, and an active movement exists for the wait to
  block on.
- "After she arrives" is free: the action ends with a `WaitPhase` that
  blocks until the walk's completion signal fires. The speech is one more
  `EffectPhase` behind it, so it can only run once the walk is done. A
  no-op walk (already at the edge) short-circuits the wait to success, so
  the line still fires; a walk that never completes (safety timeout) takes
  the dispatcher's failure path and the line is not spoken.

`speak=None` builds a silent walk (no trailing speech phase) — that's the
"just wander" idle action, sharing this one animated-walk path.
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from .dispatcher import Action
from .phases import EffectPhase, ScheduleFn, WaitPhase

if TYPE_CHECKING:
    from ..movement.manager import MovementManager


# Matches make_movement_action: generous cap that only trips on genuine bugs.
WALK_SAFETY_TIMEOUT_MS = 30_000


def make_walk_and_speak_action(
    movement: "MovementManager",
    schedule: ScheduleFn,
    *,
    direction: tuple[int, int],
    speak: Optional[Callable[[], None]] = None,
    distance: Optional[float] = None,
    safety_timeout_ms: int = WALK_SAFETY_TIMEOUT_MS,
) -> Action:
    """Build an Action that walks `direction` (animated), then calls `speak`.

    `speak` is the side effect that shows the line (typically
    ``lambda: orchestrator.speak_line(line)``). It runs once, after the
    walk's completion signal. Pass ``speak=None`` for a silent wander.

    `distance` is how far to walk, in px; ``None`` uses the manager's
    default stride.
    """

    def _kick_off() -> None:
        movement.apply_directional_walk(direction, distance)

    phases = [
        EffectPhase(_kick_off),
        WaitPhase(
            subscribe=movement.add_completion_listener,
            schedule=schedule,
            safety_timeout_ms=safety_timeout_ms,
            # No active movement means the walk no-op'd (already at the edge);
            # nothing will ever signal completion, so complete immediately
            # instead of stalling for the full safety timeout.
            precondition=lambda: movement.has_active_movement,
        ),
    ]
    if speak is not None:
        phases.append(EffectPhase(speak))

    return Action(
        kind="walk_and_speak",
        failure_state_key=None,
        phases=phases,
        metadata={"direction": direction},
    )
