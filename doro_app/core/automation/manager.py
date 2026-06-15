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
            ├─ class in allowlist → cursor-free click via A11yClickerPort
            │                       (UIA InvokePattern at production)
            ├─ no InvokePattern at target → NOT_INVOCABLE, no click
            └─ class miss / kill-switch / esc → no click, audit-log it
          (always) transition_coordinator.end()

Cursor-free click: the click path used to call `InputBackendPort.click_left`
which synthesised a real OS mouse event (pynput → SetCursorPos + mouse_event)
and visibly moved the user's cursor on every click. That has been replaced
with `A11yClickerPort.try_invoke_at` — UIA's InvokePattern fires the
element's "click" action without touching the OS cursor. Elements that
don't expose InvokePattern (canvas-rendered widgets / custom controls)
surface as NOT_INVOCABLE so the LLM can retry rather than the user's
cursor jumping unexpectedly.

Click coordinate sourcing: the manager prefers `click_target_provider()`
(typically `MovementManager.last_target_physical`) over the live foot
position. Foot sampling falls back when there is no recent MOVE target.
This lets clicks land on edge-of-screen targets that the foot cannot
reach (window clamps to screen, so the foot's reachable region is
`[w/2, screen_w - w/2] × [h-1, screen_h - 1]`).

Sequencing with movement: previously this manager polled
`movement_active_provider` and deferred the wind-up while Doro was
walking, with a 5s safety cap. That coordination now lives in
`ActionDispatcher` — callers dispatch a `MovementAction` then a
`ClickAction`, and the dispatcher only starts the click after the
movement listener fires. `execute_click` here assumes the caller has
already arranged for Doro to be at the target.

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

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TYPE_CHECKING

from ...constants import (
    CLICK_DRAG_GRACE_MS,
    CLICK_PROXIMITY_THRESHOLD_PX,
    CLICK_RATE_LIMIT_MS,
    CLICK_WIND_UP_MS,
    KILL_SWITCH_ESC_COUNT,
    KILL_SWITCH_ESC_WINDOW_MS,
)
from ...utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...utils.config_manager import ConfigManager
    from ..a11y import A11yClickerPort
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
    REJECTED_BY_ALLOWLIST = "rejected-by-allowlist"
    REJECTED_NOT_FOREGROUND = "rejected-not-foreground"  # allowlisted class but not the focused window
    DRAG_GRACE_EXCEEDED = "drag-grace-exceeded"
    ABORTED_BY_ESC = "esc-abort"
    NOT_INVOCABLE = "not-invocable"        # UIA found no InvokePattern at target
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
        a11y_clicker: Optional["A11yClickerPort"] = None,
        on_esc_extra: Optional[Callable[[], None]] = None,
        schedule: ScheduleFn,
        marshal: Optional[Callable[[Callable[[], None]], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        wind_up_ms: int = CLICK_WIND_UP_MS,
        rate_limit_ms: int = CLICK_RATE_LIMIT_MS,
        drag_grace_ms: int = CLICK_DRAG_GRACE_MS,
        click_proximity_px: int = CLICK_PROXIMITY_THRESHOLD_PX,
    ) -> None:
        self._config = config_manager
        self._window = window
        self._backend = input_backend
        self._transitions = transition_coordinator
        self._wind_up_animator = wind_up_animator
        self._warning_overlay = warning_overlay
        self._bounds_provider = bounds_provider
        self._click_target_provider = click_target_provider
        # Cursor-free click backend — UIA InvokePattern in production,
        # `NullA11yClicker` on non-Windows (so the click is dropped with
        # NOT_INVOCABLE rather than synthesising a mouse event that would
        # move the user's cursor). When None the manager treats it as
        # "no clicker wired" → NOT_INVOCABLE for every attempt.
        self._a11y_clicker = a11y_clicker
        # Additional Esc hook fired alongside the built-in click-abort
        # handling. Used by the application to forward Esc to the
        # ActionDispatcher so any queued click (or in-flight movement
        # waiter) is cancelled too.
        self._on_esc_extra = on_esc_extra
        self._schedule = schedule
        self._clock = clock
        # M2 foreground gate: any Doro-owned top-level window (sprite,
        # chat dialog, click-warning overlay, settings frame) shares this
        # PID, so the gate can treat them all as "aligned" without
        # enumerating Qt's window list.
        self._self_pid: int = os.getpid()

        self._wind_up_ms = int(wind_up_ms)
        self._rate_limit_ms = int(rate_limit_ms)
        self._drag_grace_ms = int(drag_grace_ms)
        self._click_proximity_px = int(click_proximity_px)

        self._pending: Optional[_PendingClick] = None
        self._last_click_at: float = 0.0
        self._abort_pending: bool = False

        # Kill-switch state — three Esc presses within a short window
        # globally disables automation by writing config.mouse_enabled=False.
        self._kill_switch_engaged: bool = False
        self._esc_press_times: list[float] = []

        # Bookkeeping for tests / debug; production never reads these.
        # Bounded — the manager lives for the whole app session and every
        # click attempt appends one entry.
        self.outcomes: deque[ClickOutcome] = deque(maxlen=256)

        # Terminal-outcome listeners — `ClickAction` (via the
        # ActionDispatcher) subscribes here to know when one click is
        # finished so it can release the action queue. Listeners are
        # callable as `cb(outcome, detail)` and fire exactly once per
        # call to `_finalize`.
        self._outcome_listeners: list[Callable[["ClickOutcome", str], None]] = []

        # Esc fires on the pynput keyboard-listener thread. Everything the
        # callback does — cancelling the dispatcher, flipping state via
        # QMovie, writing kill-switch state to QSettings — must run on the
        # Qt main thread. `marshal` is the trampoline: production wires it
        # to a queued signal that lives on the main thread; tests inject a
        # synchronous default so existing behaviour is preserved.
        self._marshal = marshal if marshal is not None else (lambda fn: fn())
        # The backend MUST guarantee that the callback only fires on Esc
        # and that no other key data is recorded.
        self._backend.install_esc_listener(self._dispatch_esc_to_main)

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
        # outcome reported. Exception: if the user has flipped mouse_enabled
        # back on (settings dialog persisted True) we treat that as a
        # deliberate re-enable and silently clear the kill-switch — without
        # this, re-ticking the checkbox would *look* effective in the UI
        # while every click stayed silently dropped until restart.
        if self._kill_switch_engaged:
            if self._config.automation.mouse_enabled:
                self.reset_kill_switch()
            else:
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
        # `is_busy=True` and the future outcome listener notification.
        return ClickOutcome.FIRED  # provisional; final outcome via listener

    def add_outcome_listener(
        self, callback: Callable[["ClickOutcome", str], None]
    ) -> Callable[[], None]:
        """Register *callback* to receive the next terminal click outcome.

        `ClickAction` uses this so the ActionDispatcher can wait for the
        click pipeline to finish without polling `is_busy`. Returns an
        `unsubscribe` callable; listeners persist across clicks until
        they unsubscribe.
        """
        self._outcome_listeners.append(callback)

        def _unsubscribe() -> None:
            try:
                self._outcome_listeners.remove(callback)
            except ValueError:
                pass

        return _unsubscribe

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

        # M3: Recheck Esc immediately. Without this an Esc arriving
        # between the wind-up timer expiry and this method's entry was
        # silently dropped — the click would still fire.
        if self._abort_pending:
            self._finalize(ClickOutcome.ABORTED_BY_ESC, "esc during fire path")
            return

        # Prefer the most recent [MOVE:to] target — the foot may not have
        # reached it (window clamps to screen, so edge targets like the
        # browser bookmark bar / window controls land outside foot reach).
        # Falling back to the foot keeps clicks without a prior MOVE working.
        target = self._click_target_provider() if self._click_target_provider else None
        fx, fy = self._window.foot_position_physical()
        if target is not None:
            cx, cy = target
            source = "target"
            # Proximity guard: even with target-consumption upstream, an LLM
            # may still emit a `[move:to]` to coordinates Doro couldn't reach
            # (edge clamp, partial move) or hallucinate a target that's
            # nowhere near the foot. If we'd click somewhere Doro visibly
            # isn't, fall back to the foot — less surprising than a phantom
            # click across the screen.
            # The threshold constant is in logical pixels but distances
            # here are physical — scale by DPR so high-DPI screens don't
            # shrink the allowed range.
            try:
                dpr = self._window.device_pixel_ratio() or 1.0
            except Exception:  # pragma: no cover - defensive
                dpr = 1.0
            proximity_px = self._click_proximity_px * dpr
            dist = math.hypot(cx - fx, cy - fy)
            if dist > proximity_px:
                logger.info(
                    "click target (%d,%d) is %dpx from foot (%d,%d) — "
                    "exceeds %dpx proximity, falling back to foot",
                    cx, cy, int(dist), fx, fy, int(proximity_px),
                )
                cx, cy = fx, fy
                source = "foot"
        else:
            cx, cy = fx, fy
            source = "foot"

        # Safety clamp to Doro's current screen: a stale or LLM-
        # miscomputed target may land off-screen. Use the live screen
        # geometry (origin + size) so secondary monitors with non-zero
        # origins are clamped to themselves rather than into the primary
        # monitor's range.
        sl, st, sw, sh = self._window.screen_geometry_physical()
        cx = max(sl, min(sl + sw - 1, int(cx)))
        cy = max(st, min(st + sh - 1, int(cy)))

        # Self-clicking trap: Doro's main window AND the red warning frame
        # both sit on top of the click target (sprite-foot anchor makes
        # Doro overlap the target; the frame is WindowStaysOnTopHint by
        # design). If we leave them visible / hit-testable, the OS-level
        # WindowFromPoint query that backs read_window_class_at lands on
        # our own Qt windows instead of the real target. Hide / pass-
        # through both before the class read so the allowlist check sees
        # the target window's actual class. The UIA InvokePattern path
        # doesn't move the cursor at all, but `ControlFromPoint` still
        # walks the same hit-test tree, so keeping Doro transparent
        # during the invoke is belt-and-suspenders.
        if self._warning_overlay is not None:
            try:
                self._warning_overlay.end()
            except Exception:  # pragma: no cover - defensive
                logger.exception("WarningOverlay.end() (pre-fire) raised")
        try:
            self._window.set_mouse_transparent(True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("set_mouse_transparent(True) failed")

        class_name: Optional[str] = None
        invoke_ok = False
        try:
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

            # M2: Foreground verification. The allowlist gates which
            # window CLASSES are clickable; this extra check refuses to
            # click an allowlisted class that happens to sit under the
            # cursor but isn't actually the focused window — e.g. a
            # background browser visible behind a different foreground
            # app. Backend methods return None on platforms that don't
            # implement them; in that case we skip the gate (preserves
            # current X11/macOS behaviour).
            #
            # The PID check lets any Doro-owned top-level window (chat
            # dialog, click-warning overlay, settings frame, …) count as
            # aligned — UIA InvokePattern doesn't need the target to have
            # OS focus, so Doro holding focus on its own UI is fine.
            try:
                target_hwnd = self._backend.read_handle_at(cx, cy)
                fg_hwnd = self._backend.read_foreground_window_handle()
            except Exception:  # pragma: no cover - defensive
                target_hwnd = None
                fg_hwnd = None
            fg_pid: Optional[int] = None
            if fg_hwnd is not None:
                try:
                    fg_pid = self._backend.read_pid_of_handle(fg_hwnd)
                except Exception:  # pragma: no cover - defensive
                    fg_pid = None
            if (
                target_hwnd is not None
                and fg_hwnd is not None
                and target_hwnd != fg_hwnd
                and fg_pid != self._self_pid
            ):
                fg_class: Optional[str] = None
                try:
                    fg_class = self._backend.read_class_of_handle(fg_hwnd)
                except Exception:  # pragma: no cover - defensive
                    fg_class = None
                fg_label = (
                    f"{fg_hwnd} class={fg_class!r}" if fg_class else str(fg_hwnd)
                )
                self._finalize(
                    ClickOutcome.REJECTED_NOT_FOREGROUND,
                    f"target window ({target_hwnd}) is not foreground ({fg_label})",
                )
                return

            # M3: Recheck Esc one more time — the class read can be
            # slow on Windows and the foreground check adds another
            # round-trip. Without this the click still fires if Esc
            # arrived during the gates above.
            if self._abort_pending:
                self._finalize(ClickOutcome.ABORTED_BY_ESC, "esc before invoke")
                return

            # Cursor-free click via UIA InvokePattern. The clicker returns
            # False whenever the element under (cx, cy) doesn't expose an
            # InvokePattern (canvas, custom widgets) — we surface that as
            # NOT_INVOCABLE rather than falling back to a synthetic mouse
            # event, because the whole point of this path is that the
            # user's OS cursor never moves.
            if self._a11y_clicker is None:
                self._finalize(
                    ClickOutcome.NOT_INVOCABLE,
                    f"no a11y clicker wired ({cx},{cy}) class={class_name!r}",
                )
                return
            # Scope the UIA hit-test to ``target_hwnd`` so Doro's sprite
            # (visible to UIA even with ``WS_EX_TRANSPARENT`` set, because
            # ``ControlFromPoint`` walks bounding rects, not Win32 hit
            # flags) cannot shadow the real target. ``target_hwnd`` was
            # resolved with ``CWP_SKIPTRANSPARENT`` so it already points
            # at the actual target window (Chrome / Edge / ...). ``None``
            # on platforms without Win32 falls back to unscoped lookup.
            try:
                invoke_ok = self._a11y_clicker.try_invoke_at(
                    cx, cy, hwnd=target_hwnd,
                )
            except Exception:  # pragma: no cover - clicker should not raise
                logger.exception("a11y clicker.try_invoke_at raised")
                invoke_ok = False
            if not invoke_ok:
                self._finalize(
                    ClickOutcome.NOT_INVOCABLE,
                    f"no InvokePattern at ({cx},{cy}) class={class_name!r}",
                )
                return
        finally:
            try:
                self._window.set_mouse_transparent(False)
            except Exception:  # pragma: no cover
                logger.exception("set_mouse_transparent(False) failed")

        self._last_click_at = self._clock()
        self._finalize(
            ClickOutcome.FIRED,
            f"invoke@({cx},{cy}) source={source} class={class_name!r}",
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

        # Notify outcome listeners after recording, so listeners can read
        # `outcomes[-1]` and see the same value they were just handed.
        for listener in list(self._outcome_listeners):
            try:
                listener(outcome, detail)
            except Exception:  # pragma: no cover - listeners should not raise
                logger.exception("Click outcome listener raised")

    # ------------------------------------------------------------------ Esc / kill-switch

    def _dispatch_esc_to_main(self) -> None:
        """Backend (off-thread) entry — hop to the main thread before
        touching Qt-bound state."""
        self._marshal(self._on_esc_pressed)

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

        # Forward to the optional extra hook (typically
        # `ActionDispatcher.cancel_current`). Runs after the local
        # bookkeeping so the dispatcher sees up-to-date state.
        if self._on_esc_extra is not None:
            try:
                self._on_esc_extra()
            except Exception:  # pragma: no cover - hook must not break Esc
                logger.exception("on_esc_extra hook raised")

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

    def reset_kill_switch(self) -> None:
        """Re-arm the manager after a kill-switch engagement.

        Called by the settings dialog when the user re-ticks
        ``mouse_enabled``; also called from inside ``execute_click`` as
        a self-heal when config says enabled but the flag is still True
        (race between the dialog save and the next click).
        """
        if self._kill_switch_engaged:
            logger.info("Kill-switch reset by user re-enable")
        self._kill_switch_engaged = False
        self._esc_press_times = []

    def cancel_pending_click(self, reason: str = "drag") -> bool:
        """Abort an in-flight wind-up without triggering kill-switch logic.

        Used by the drag handler in ``DoroApp`` so the click that was
        already past the dispatcher (running in the manager's wind-up)
        also unwinds — otherwise the timer would still fire and click
        at the post-drag foot position. Returns True if a wind-up was
        cancelled, False if there was nothing in flight.
        """
        if self._pending is None:
            return False
        self._abort_pending = True
        logger.info(f"In-flight click cancelled (reason={reason})")
        return True

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
