"""AutomationManager — gatekeeper for synthetic left-click events.

Lifecycle of one `[mouse:click]`:

    execute_click()
      ├─ enabled? rate-limited? kill-switch tripped?
      ├─ transition_coordinator.begin()       (idle suppression)
      ├─ start wind-up timer (CLICK_WIND_UP_MS)
      │     (during this window the user can press Esc to cancel; the
      │      red warning overlay frames the click target so it's visible)
      └─ on wind-up expiry → _on_wind_up_finished()
            ├─ if left button is being held → enter drag-grace loop
            ├─ pick click coord: last [MOVE:to] target if any, else Doro's foot
            ├─ read window class at that coord
            ├─ class in allowlist → fire click via InputBackendPort
            └─ class miss / kill-switch / esc → no click, audit-log it
          (always) transition_coordinator.end()

Click coordinate sourcing: the manager prefers `click_target_provider()`
(typically `MovementManager.last_target_physical`) over the live foot
position. Foot sampling falls back when there is no recent MOVE target.
This lets clicks land on edge-of-screen targets that the foot cannot
reach (window clamps to screen, so the foot's reachable region is
`[w/2, screen_w - w/2] × [h-1, screen_h - 1]`).

Safety: the user cancels via Esc (1.5s wind-up window), or the 3-Esc
kill-switch globally disables automation. The red warning overlay
visualises the actual click coordinate during wind-up so the user can
verify before it fires. Dragging Doro during wind-up no longer
redirects the click — only Esc does.

The manager intentionally has no Qt dependency in its hot path — wind-up
expiry is driven by a caller-supplied scheduler so tests can advance
"time" synchronously. In production, the scheduler is a thin wrapper
around `QtCore.QTimer.singleShot`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TYPE_CHECKING

from ...constants import (
    CLICK_DRAG_GRACE_MS,
    CLICK_RATE_LIMIT_MS,
    CLICK_WIND_UP_MS,
    KILL_SWITCH_ESC_COUNT,
    KILL_SWITCH_ESC_WINDOW_MS,
)
from ...utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...utils.config_manager import ConfigManager
    from ..state.transition_coordinator import TransitionCoordinator
    from .port import (
        AutomationWindowPort,
        ClickWarningOverlayPort,
        InputBackendPort,
        WindUpAnimatorPort,
    )

    BoundsProvider = Callable[[], Optional[tuple[int, int, int, int]]]


logger = get_logger("doro.automation")


class ClickOutcome(Enum):
    """Terminal outcome of one `execute_click` invocation."""

    DISABLED = "disabled"                 # mouse_enabled was False at execute time
    RATE_LIMITED = "rate-limited"         # too soon after previous click
    KILL_SWITCH = "kill-switch"           # three-Esc kill-switch is engaged
    BUSY = "busy"                         # already mid-wind-up
    REJECTED_BY_ALLOWLIST = "redirect-blocked"
    DRAG_GRACE_EXCEEDED = "drag-grace-exceeded"
    ABORTED_BY_ESC = "esc-abort"
    FIRED = "fired"


# Caller-supplied scheduler signature. Production wires this to
# `QtCore.QTimer.singleShot(int_ms, fn)`. Tests pass a controllable scheduler.
ScheduleFn = Callable[[int, Callable[[], None]], None]


@dataclass
class _PendingClick:
    """Internal state held across the wind-up timer."""

    started_at: float
    grace_deadline: Optional[float] = None  # set when entering drag-grace loop


class AutomationManager:
    """Coordinator for `[mouse:click]` execution.

    Args:
        config_manager: Read `mouse_enabled` + allowlist at fire time, and
            *write* `mouse_enabled=False` when the kill-switch trips.
        window: Doro window port (foot position + transparent toggle).
        input_backend: Synthetic-event backend (pynput or fake).
        transition_coordinator: Existing state coordinator — manager calls
            `begin()` / `end()` so `IdleBehaviorManager` won't preempt the
            wind-up GIF.
        schedule: Function used to schedule the wind-up timer expiry. In
            production, ``lambda ms, fn: QtCore.QTimer.singleShot(ms, fn)``.
            Tests inject a manual scheduler.
        clock: Source of monotonic seconds (overridable for tests).
        wind_up_ms / rate_limit_ms / drag_grace_ms: tunables; defaults pull
            from :mod:`doro_app.constants`.
    """

    def __init__(
        self,
        *,
        config_manager: "ConfigManager",
        window: "AutomationWindowPort",
        input_backend: "InputBackendPort",
        transition_coordinator: Optional["TransitionCoordinator"] = None,
        wind_up_animator: Optional["WindUpAnimatorPort"] = None,
        warning_overlay: Optional["ClickWarningOverlayPort"] = None,
        bounds_provider: Optional["BoundsProvider"] = None,
        click_target_provider: Optional[Callable[[], Optional[tuple[int, int]]]] = None,
        schedule: ScheduleFn,
        clock: Callable[[], float] = time.monotonic,
        wind_up_ms: int = CLICK_WIND_UP_MS,
        rate_limit_ms: int = CLICK_RATE_LIMIT_MS,
        drag_grace_ms: int = CLICK_DRAG_GRACE_MS,
    ) -> None:
        self._config = config_manager
        self._window = window
        self._backend = input_backend
        self._transitions = transition_coordinator
        self._wind_up_animator = wind_up_animator
        self._warning_overlay = warning_overlay
        self._bounds_provider = bounds_provider
        self._click_target_provider = click_target_provider
        self._schedule = schedule
        self._clock = clock

        self._wind_up_ms = int(wind_up_ms)
        self._rate_limit_ms = int(rate_limit_ms)
        self._drag_grace_ms = int(drag_grace_ms)

        self._pending: Optional[_PendingClick] = None
        self._last_click_at: float = 0.0
        self._abort_pending: bool = False

        # Kill-switch state — three Esc presses within a short window
        # globally disables automation by writing config.mouse_enabled=False.
        self._kill_switch_engaged: bool = False
        self._esc_press_times: list[float] = []

        # Bookkeeping for tests / debug; production never reads these.
        self.outcomes: list[ClickOutcome] = []

        # Install the Esc listener. The backend MUST guarantee that the
        # callback only fires on Esc and that no other key data is recorded.
        self._backend.install_esc_listener(self._on_esc_pressed)

        logger.info(
            "AutomationManager initialized "
            f"(enabled={config_manager.automation.mouse_enabled}, "
            f"allowlist={config_manager.automation.mouse_target_allowlist})"
        )

    # ------------------------------------------------------------------ Public API

    @property
    def is_busy(self) -> bool:
        """True if a wind-up is currently in flight."""
        return self._pending is not None

    @property
    def is_kill_switch_engaged(self) -> bool:
        return self._kill_switch_engaged

    def execute_click(self) -> ClickOutcome:
        """Process one `[mouse:click]` bracket.

        This is the only public entry point the chat orchestrator calls.
        Returns the synchronous outcome — for accepted clicks, that outcome
        is the *eventual* outcome decided when the wind-up timer expires
        (delivered via the audit log; the orchestrator should not block on
        it).
        """
        # Order: kill-switch beats config check, since kill-switch flips
        # mouse_enabled=False as a side effect and we want the more specific
        # outcome reported.
        if self._kill_switch_engaged:
            return self._record(ClickOutcome.KILL_SWITCH, "kill-switch engaged")

        if not self._config.automation.mouse_enabled:
            return self._record(ClickOutcome.DISABLED, "mouse_enabled=False")

        if self._pending is not None:
            return self._record(ClickOutcome.BUSY, "wind-up already in progress")

        now = self._clock()
        since_last = (now - self._last_click_at) * 1000.0 if self._last_click_at else float("inf")
        if since_last < self._rate_limit_ms:
            return self._record(
                ClickOutcome.RATE_LIMITED,
                f"only {since_last:.0f}ms since last click (min {self._rate_limit_ms}ms)",
            )

        # All preflight checks passed — start the wind-up.
        self._pending = _PendingClick(started_at=now)
        self._abort_pending = False
        if self._transitions is not None:
            try:
                self._transitions.begin()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"TransitionCoordinator.begin() raised: {exc}")
        if self._wind_up_animator is not None:
            try:
                self._wind_up_animator.begin()
            except Exception:  # pragma: no cover - defensive
                logger.exception("WindUpAnimator.begin() raised")
        if self._warning_overlay is not None:
            try:
                bounds = self._bounds_provider() if self._bounds_provider else None
                self._warning_overlay.begin(bounds)
            except Exception:  # pragma: no cover - defensive
                logger.exception("WarningOverlay.begin() raised")

        logger.info(f"Click wind-up starting (duration={self._wind_up_ms}ms)")
        self._schedule(self._wind_up_ms, self._on_wind_up_finished)
        # Returning FIRED here would be a lie — the click hasn't fired yet.
        # We surface a synthetic "accepted" outcome via the side effect of
        # `is_busy=True` and the future audit log entry.
        return ClickOutcome.FIRED  # provisional; final outcome via audit log

    def shutdown(self) -> None:
        """Tear down the input backend's listener thread."""
        try:
            self._backend.shutdown()
        except Exception:  # pragma: no cover - best-effort
            logger.exception("Backend shutdown raised")

    # ------------------------------------------------------------------ Wind-up callbacks

    def _on_wind_up_finished(self) -> None:
        if self._pending is None:
            # Already aborted (e.g. Esc) — nothing to do.
            return

        if self._abort_pending:
            self._finalize(ClickOutcome.ABORTED_BY_ESC, "esc pressed during wind-up")
            return

        if self._backend.is_left_button_pressed():
            # User is mid-drag at wind-up expiry. Enter grace loop.
            self._pending.grace_deadline = self._clock() + (self._drag_grace_ms / 1000.0)
            logger.info(
                f"Wind-up finished but left button held; entering {self._drag_grace_ms}ms grace"
            )
            self._schedule(50, self._check_grace)
            return

        self._fire_now()

    def _check_grace(self) -> None:
        if self._pending is None or self._pending.grace_deadline is None:
            return
        if self._abort_pending:
            self._finalize(ClickOutcome.ABORTED_BY_ESC, "esc during grace")
            return
        if not self._backend.is_left_button_pressed():
            self._fire_now()
            return
        if self._clock() >= self._pending.grace_deadline:
            self._finalize(ClickOutcome.DRAG_GRACE_EXCEEDED, "user held left button past grace")
            return
        self._schedule(50, self._check_grace)

    def _fire_now(self) -> None:
        """Pick click coord (target if available, else foot), validate, click."""
        if self._pending is None:
            return

        # Prefer the most recent [MOVE:to] target — the foot may not have
        # reached it (window clamps to screen, so edge targets like the
        # browser bookmark bar / window controls land outside foot reach).
        # Falling back to the foot keeps clicks without a prior MOVE working.
        target = self._click_target_provider() if self._click_target_provider else None
        if target is not None:
            cx, cy = target
            source = "target"
        else:
            cx, cy = self._window.foot_position_physical()
            source = "foot"

        # Safety clamp to screen: a stale or LLM-miscomputed target may
        # land off-screen. Clamp so the synthetic event always points at a
        # real pixel rather than relying on OS-level handling of OOB coords.
        sw, sh = self._window.screen_size_physical()
        cx = max(0, min(sw - 1, int(cx)))
        cy = max(0, min(sh - 1, int(cy)))

        class_name = self._backend.read_window_class_at(cx, cy)
        print(
            f"[doro click] fire source={source} coord=({cx},{cy}) class={class_name!r}",
            flush=True,
        )

        if not self._is_allowlisted(class_name):
            self._finalize(
                ClickOutcome.REJECTED_BY_ALLOWLIST,
                f"window class {class_name!r} not in allowlist",
            )
            return

        # Brief transparent-toggle window to avoid Doro hit-testing herself.
        # See plan §"Self-clicking trap".
        try:
            self._window.set_mouse_transparent(True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("set_mouse_transparent(True) failed")
        try:
            self._backend.click_left(cx, cy)
        except Exception:  # pragma: no cover - backend failure should not strand the lock
            logger.exception("click_left raised")
        finally:
            try:
                self._window.set_mouse_transparent(False)
            except Exception:  # pragma: no cover
                logger.exception("set_mouse_transparent(False) failed")

        self._last_click_at = self._clock()
        self._finalize(
            ClickOutcome.FIRED,
            f"click@({cx},{cy}) source={source} class={class_name!r}",
        )

    def _finalize(self, outcome: ClickOutcome, detail: str) -> None:
        """Single exit path — every wind-up flow must end here so the
        transition lock is always released."""
        if self._warning_overlay is not None:
            try:
                self._warning_overlay.end()
            except Exception:  # pragma: no cover - defensive
                logger.exception("WarningOverlay.end() raised")
        if self._wind_up_animator is not None:
            try:
                self._wind_up_animator.end()
            except Exception:  # pragma: no cover - defensive
                logger.exception("WindUpAnimator.end() raised")
        if self._transitions is not None:
            try:
                self._transitions.end()
            except Exception:  # pragma: no cover - defensive
                logger.warning("TransitionCoordinator.end() raised", exc_info=True)
        self._pending = None
        self._abort_pending = False
        self._record(outcome, detail)

    # ------------------------------------------------------------------ Esc / kill-switch

    def _on_esc_pressed(self) -> None:
        """Called by the input backend each time the user presses Esc.

        Two behaviours overlap:
          (a) if a wind-up is in flight, abort it;
          (b) accumulate towards the three-Esc kill-switch.
        """
        now = self._clock()
        # Drop press times outside the rolling window.
        window_s = KILL_SWITCH_ESC_WINDOW_MS / 1000.0
        self._esc_press_times = [t for t in self._esc_press_times if (now - t) <= window_s]
        self._esc_press_times.append(now)

        if self._pending is not None:
            self._abort_pending = True
            logger.info("Esc pressed during wind-up — click will be aborted")

        if len(self._esc_press_times) >= KILL_SWITCH_ESC_COUNT and not self._kill_switch_engaged:
            self._engage_kill_switch()

    def _engage_kill_switch(self) -> None:
        self._kill_switch_engaged = True
        logger.warning(
            f"Kill-switch engaged ({KILL_SWITCH_ESC_COUNT} Esc presses in "
            f"<{KILL_SWITCH_ESC_WINDOW_MS}ms) — disabling automation"
        )
        try:
            self._config.update_automation(mouse_enabled=False)
            self._config.save()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to persist kill-switch state to config")
        if self._pending is not None:
            self._abort_pending = True

    # ------------------------------------------------------------------ Helpers

    def _is_allowlisted(self, class_name: Optional[str]) -> bool:
        """Prefix match (case-insensitive). Apps on Windows expose multiple
        widget-hierarchy classes off the same prefix, e.g. Chrome → "Chrome_
        WidgetWin_1" / "Chrome_RenderWidgetHostHWND". Treating allowlist
        entries as prefixes lets one entry ("Chrome") cover that family
        without enumerating every variant."""
        if not class_name:
            return False
        allowlist = self._config.automation.mouse_target_allowlist
        lowered = class_name.strip().lower()
        return any(
            lowered.startswith(item.strip().lower())
            for item in allowlist
            if item and item.strip()
        )

    def _record(self, outcome: ClickOutcome, detail: str) -> ClickOutcome:
        self.outcomes.append(outcome)
        logger.info(f"[automation] {outcome.value}: {detail}")
        # Mirror to stdout so users diagnosing "why didn't my click fire?"
        # don't need to dig through logger output. Every click attempt
        # ends with exactly one _record() call, so this is one line per
        # attempt — not noisy.
        print(f"[doro click] outcome={outcome.value} {detail}", flush=True)
        return outcome

    # ------------------------------------------------------------------ Test hooks

    def _complete_wind_up_for_test(self) -> None:
        """Synchronously trigger wind-up expiry (testing only)."""
        self._on_wind_up_finished()

    def _check_grace_for_test(self) -> None:
        """Synchronously advance one grace-loop iteration (testing only)."""
        self._check_grace()
