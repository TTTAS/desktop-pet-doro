"""Factory for `ClickAction` — wraps AutomationManager as an Action.

ClickAction is currently a thin wrapper: an EffectPhase that kicks
`AutomationManager.execute_click()` and a custom await-phase that
resolves when the manager publishes its terminal `ClickOutcome`. The
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

from typing import Callable, Optional, TYPE_CHECKING

from .dispatcher import Action
from .phases import EffectPhase, Phase, ScheduleFn
from .service import CLICK_FAILED_STATE_KEY

if TYPE_CHECKING:
    from ..automation.manager import AutomationManager, ClickOutcome


__all__ = ["CLICK_FAILED_STATE_KEY", "make_click_action"]

# Safety cap for the await-outcome phase. Production click pipelines
# resolve in ~1.5s (wind-up) plus optional drag grace. 30s is the same
# generous ceiling we use for movement.
CLICK_SAFETY_TIMEOUT_MS = 30_000


class _AwaitClickOutcomePhase:
    """Phase that completes when AutomationManager publishes a terminal outcome.

    Lives in this module (not phases.py) because the outcome→done/fail
    mapping is click-specific: only `ClickOutcome.FIRED` counts as
    completion; every other terminal outcome (kill-switch, allowlist
    rejection, Esc abort, drag-grace exceeded) is a failure.
    """

    def __init__(
        self,
        automation: "AutomationManager",
        schedule: ScheduleFn,
        safety_timeout_ms: int = CLICK_SAFETY_TIMEOUT_MS,
    ) -> None:
        self._automation = automation
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
        from ..automation.manager import ClickOutcome

        def _on_outcome(outcome: "ClickOutcome", detail: str) -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            if outcome == ClickOutcome.FIRED:
                on_done()
            else:
                on_fail(f"{outcome.value}: {detail}")

        def _timeout() -> None:
            if self._cancelled or self._fired:
                return
            self._fired = True
            self._do_unsubscribe()
            on_fail("click-timeout")

        self._unsubscribe = self._automation.add_outcome_listener(_on_outcome)
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
            except Exception:  # pragma: no cover - non-fatal
                pass


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
    `_AwaitClickOutcomePhase` resolves when the manager finalizes.
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
        _AwaitClickOutcomePhase(
            automation=automation,
            schedule=schedule,
            safety_timeout_ms=safety_timeout_ms,
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
