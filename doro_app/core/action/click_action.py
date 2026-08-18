"""Factory for `ClickAction` — wraps AutomationManager as an Action.

ClickAction is currently a thin wrapper: an EffectPhase that kicks
`AutomationManager.execute_click()` and a `WaitPhase` (configured with
`_resolve_click_outcome`) that resolves when the manager publishes its
terminal `ClickOutcome`. The
manager continues to own the click pipeline internals (wind-up timer,
warning overlay, Esc handling, drag grace, allowlist, kill switch). A
future refactor can decompose those into discrete phases — see
plan §3 "follow-up" — but the action shape is in place now so the
dispatcher can sequence movement → click without polling.

The dispatcher already captures and restores the pre-action display
state; AutomationManager's `_QtWindUpAnimatorAdapter` also saves and
restores. The two no-op each other on the restore side because the
dispatcher's `set_state` is skipped when the current state already
matches `_pre_action_state`.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .dispatcher import Action
from .phases import EffectPhase, Phase, ScheduleFn, WaitPhase
from .service import CLICK_FAILED_STATE_KEY

if TYPE_CHECKING:
    from ..automation.manager import AutomationManager, ClickOutcome


__all__ = ["CLICK_FAILED_STATE_KEY", "make_click_action"]

# Safety cap for the await-outcome phase. Production click pipelines
# resolve in ~1.5s (wind-up) plus optional drag grace. 30s is the same
# generous ceiling we use for movement.
CLICK_SAFETY_TIMEOUT_MS = 30_000


def _resolve_click_outcome(outcome: "ClickOutcome", detail: str) -> Optional[str]:
    """Map a terminal `ClickOutcome` to a `WaitPhase` result.

    Click-specific and therefore local to this module: only
    `ClickOutcome.FIRED` counts as completion (return ``None``); every
    other terminal outcome (kill-switch, allowlist rejection, Esc abort,
    drag-grace exceeded, not-invocable, …) is a failure whose reason
    strings the outcome and detail together.
    """
    from ..automation.manager import ClickOutcome

    if outcome == ClickOutcome.FIRED:
        return None
    return f"{outcome.value}: {detail}"


def make_click_action(
    automation: "AutomationManager",
    schedule: ScheduleFn,
    *,
    safety_timeout_ms: int = CLICK_SAFETY_TIMEOUT_MS,
) -> Action:
    """Build an Action that drives one click attempt to completion.

    The EffectPhase synchronously starts the click pipeline (preflight,
    wind-up timer, warning overlay). If preflight rejects the click
    (kill-switch / mouse disabled / rate-limited / already busy) the
    phase raises so the dispatcher reaches its failure path. Otherwise
    the `WaitPhase` resolves when the manager finalizes.
    """
    from ..automation.manager import ClickOutcome

    # Outcomes that mean "the wind-up never started" — no completion
    # listener will fire for these. We surface them as failures here so
    # the dispatcher restores cleanly instead of timing out.
    _PREFLIGHT_REJECTIONS = {
        ClickOutcome.DISABLED,
        ClickOutcome.RATE_LIMITED,
        ClickOutcome.KILL_SWITCH,
        ClickOutcome.BUSY,
    }

    def _kick() -> None:
        outcome = automation.execute_click()
        if outcome in _PREFLIGHT_REJECTIONS:
            # Raise so EffectPhase routes to on_fail; the dispatcher then
            # shows the failure GIF (if any) and restores.
            raise RuntimeError(f"preflight rejected click: {outcome.value}")

    phases: list[Phase] = [
        EffectPhase(_kick),
        # Await the manager's terminal outcome. `_resolve_click_outcome`
        # keeps the click-specific FIRED→done / else→fail mapping local to
        # this module while the generic wait/timeout/unsubscribe skeleton
        # lives in `WaitPhase`.
        WaitPhase(
            subscribe=automation.add_outcome_listener,
            schedule=schedule,
            safety_timeout_ms=safety_timeout_ms,
            resolve=_resolve_click_outcome,
            timeout_reason="click-timeout",
        ),
    ]

    return Action(
        kind="click",
        # The failure state is registered as a builtin action via
        # ActionRepository in the second PR; until then it falls back to
        # the click GIF chain (stand → idle) when set_state is called.
        # That's an acceptable placeholder — the dispatcher still does
        # the right structural thing, the user just sees the click GIF
        # again rather than a dedicated failure animation.
        failure_state_key=CLICK_FAILED_STATE_KEY,
        phases=phases,
        metadata={},
    )
