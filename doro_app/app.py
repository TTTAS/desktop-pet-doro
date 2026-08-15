"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

import os
from typing import Optional

from PySide6 import QtCore, QtWidgets

from .bootstrap import BootstrappedDependencies, bootstrap_environment
from .constants import (
    BUBBLE_AUTO_HIDE_MS,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
    CLICK_DRAG_THRESHOLD_PX,
)
from .core.action import ActionDispatcher
from .core.automation.foreground_tracker import ForegroundTracker
from .core.automation.manager import AutomationManager
from .core.chat.controller import ChatController
from .core.chat.orchestrator import ChatOrchestrator
from .core.core_manager import CoreManager
from .core.idle_behavior_manager import IdleBehaviorManager
from .core.movement.manager import MovementManager
from .core.state import StateService
from .core.state.transition_player import TransitionPlayer
from .ui.components.bubble_controller import BubbleConfig, BubbleController
from .ui.components.context_menu_controller import ContextMenuController
from .ui.controllers import ClickActionController, DialogManager, SpriteController, StateController
from .ui.events.mouse_event_handler import MouseEventHandler
from .ui.helpers import ChatUIHelper
from .ui.window import DoroWindow
from .utils.logger import get_logger
from .utils.paths import COMPANION_PROMPTS_PATH, STATE_DIR

logger = get_logger(__name__)


class DoroApp:
    """
    Application composition root.

    Responsible for:
    - Assembling all services and dependencies
    - Wiring components together
    - Creating the main window

    This separates assembly logic from the UI layer (DoroWindow).
    """

    def __init__(
        self,
        not_topmost: bool = False,
        deps: BootstrappedDependencies | None = None,
    ):
        """
        Initialize the application.

        Args:
            not_topmost: If True, window will not stay on top
        """
        deps = deps or bootstrap_environment()

        self._config_manager = deps.config_manager
        self._state_service: StateService = deps.state_service
        self._action_service = deps.action_service
        self._default_idle_gif = deps.default_idle_gif
        self._prompt_file_path = deps.prompt_file_path
        self._click_actions_path = deps.click_actions_path

        # ═════════════════════════════════════════════════════════════
        # Phase 1: Create independent components (no UI dependency)
        # ═════════════════════════════════════════════════════════════

        self._transition_player = TransitionPlayer(state_service=self._state_service)
        self._bubble_controller = BubbleController(
            config_manager=self._config_manager,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 2: Create Window (UI layer composition root)
        # ═════════════════════════════════════════════════════════════

        self.window = DoroWindow(
            state_service=self._state_service,
            not_topmost=not_topmost,
            config_manager=self._config_manager,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 3: Create UI Controllers (need window)
        # ═════════════════════════════════════════════════════════════

        self._state_controller = StateController(
            state_service=self._state_service,
            view_model=self.window.view_model,
            config_manager=self._config_manager,
        )
        self._sprite_controller = SpriteController(view_model=self.window.view_model)
        self._dialog_manager = DialogManager(
            parent_window=self.window,
            state_service=self._state_service,
            action_service=self._action_service,
        )
        # ─── A11y tree reader (Phase 1d) ─────────────────────────
        # Tree feeds the chat prompt and also lets the click warning overlay
        # frame the element under Doro's foot at wind-up time. Optional:
        # self-gates on a11y_enabled. The tracker remembers the last
        # *external* foreground window so a11y reads the app the user was
        # using, not Doro's own (self-activating) window.
        self._fg_tracker = ForegroundTracker(os.getpid())
        self._fg_tracker.start()
        self._a11y = self._maybe_build_a11y()

        self._movement_repo = deps.movement_repo
        self._movement = MovementManager(
            window=self.window,
            state_service=self._state_service,
            movement_repo=self._movement_repo,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 4: Create ChatController (needs StateController + MovementManager)
        # ═════════════════════════════════════════════════════════════

        self._chat_controller = ChatController(
            self._prompt_file_path,
            state_service=self._state_service,
            state_text_provider=lambda: self._state_controller.get_state_list_text(),
            movement_hint_provider=lambda: self._movement.instruction_text(),
            config_manager=self._config_manager,
            doro_state_provider=lambda: self._build_doro_state_text(),
            a11y_tree_provider=lambda: self._a11y.read_foreground_tree() if self._a11y else "",
        )
        # ─── Automation (Phase 1c) ───────────────────────────────
        # Optional: only constructed if mouse_enabled is True or the env var
        # was set at startup. Even when constructed, every click is gated by
        # the runtime allowlist + kill-switch — see AutomationManager.
        self._automation: AutomationManager | None = self._maybe_build_automation()

        # ─── Action dispatcher ──────────────────────────────────
        # Serializes movement + click into one ordered queue so the
        # click pipeline only runs after Doro has actually walked to the
        # target — replaces the old polling/timeout coordination that
        # used to live inside AutomationManager.
        from PySide6 import QtCore as _QtCore

        def _dispatcher_schedule(ms: int, fn) -> None:
            _QtCore.QTimer.singleShot(int(ms), fn)

        self._dispatcher_schedule = _dispatcher_schedule
        self._action_dispatcher = ActionDispatcher(
            state_service=self._state_service,
            schedule=_dispatcher_schedule,
        )

        self._chat_orchestrator = ChatOrchestrator(
            self._chat_controller,
            self._movement,
            self._state_service,
            automation=self._automation,
            action_dispatcher=self._action_dispatcher,
            schedule=_dispatcher_schedule,
        )
        self._click_action_controller = ClickActionController(
            actions_file=self._click_actions_path,
            chat_orchestrator=self._chat_orchestrator,
        )
        self._idle_behavior = IdleBehaviorManager(
            companion_file=COMPANION_PROMPTS_PATH,
            chat_orchestrator=self._chat_orchestrator,
            movement_manager=self._movement,
            state_service=self._state_service,
            idle_seconds_provider=lambda: self.window.seconds_since_last_activity(),
            mark_activity=lambda: self.window.mark_user_activity(),
            action_dispatcher=self._action_dispatcher,
            schedule=self._dispatcher_schedule,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 5: Create CoreManager (Business Logic Coordinator)
        # ═════════════════════════════════════════════════════════════

        self.core_manager = CoreManager(
            state_service=self._state_service,
            chat_controller=self._chat_controller,
            chat_orchestrator=self._chat_orchestrator,
            movement_manager=self._movement,
            transition_player=self._transition_player,
            config_manager=self._config_manager,
            a11y_service=self._a11y,
            automation_manager=self._automation,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 5: Wire Components (Connect all layers)
        # ═════════════════════════════════════════════════════════════

        self._connect_business_to_ui()
        self._connect_ui_controllers()

        # ─────────────────────────────────────────────────────────
        # Initialize StateService and restore last state
        # ─────────────────────────────────────────────────────────
        self._state_service.initialize(default_gif_path=self._default_idle_gif)

        # Register the click_action protected state (Phase 1c).
        # Must run after StateService.initialize so it can register through
        # the same channels and pick up any user-bound GIF from actions.json.
        self._action_service.bootstrap()

        # Use ConfigManager for type-safe config access
        saved_state_key = self._config_manager.app.current_state
        if not self._state_service.set_state(saved_state_key):
            self._state_service.set_state("idle")

        # Quit-time teardown: stop the pynput listener thread, the
        # a11y UIA worker pool, and the foreground-window poller before
        # the Qt event loop unwinds. A hung UIA read would otherwise
        # pin the process until the OS reaped it.
        qt_app = QtWidgets.QApplication.instance()
        if qt_app is not None:
            qt_app.aboutToQuit.connect(self._on_about_to_quit)

    def _connect_business_to_ui(self):
        """Translate domain events to UI operations (Application Layer responsibility)."""

        # ═════════════════════════════════════════════════════════════
        # Domain Events → UI Operations (Translation Layer)
        # ═════════════════════════════════════════════════════════════

        # Chat domain events
        self.core_manager.chat_response_received.connect(
            self._on_chat_response_received
        )
        self.core_manager.chat_operation_started.connect(
            self._on_chat_operation_started
        )
        self.core_manager.chat_operation_completed.connect(
            self._on_chat_operation_completed
        )
        self.core_manager.chat_error_occurred.connect(
            self._on_chat_error_occurred
        )

        # State domain events
        self.core_manager.state_changed.connect(
            self._on_domain_state_changed
        )

        # Transition domain events
        self.core_manager.transition_completed.connect(
            self._on_domain_transition_completed
        )

        # TransitionPlayer → Window (UI-specific signal for playing GIF)
        self._transition_player.transition_movie_loaded.connect(
            self.window.on_transition_movie_loaded
        )

        # ═════════════════════════════════════════════════════════════
        # BubbleController → Window connections (UI Layer internal)
        # Window reads bubble state directly from BubbleController
        # during paintEvent, so signals just trigger repaint/resize.
        # ═════════════════════════════════════════════════════════════

        self._bubble_controller.text_changed.connect(
            lambda *_: (self.window.apply_window_preferred_size(), self.window.update())
        )
        self._bubble_controller.visibility_changed.connect(
            lambda *_: self.window.update()
        )
        self._bubble_controller.repaint_requested.connect(
            self.window.update
        )
        self._bubble_controller.update_bubble_side_requested.connect(
            self.window.update_bubble_side_from_offset
        )
        self._bubble_controller.state_settings_apply_requested.connect(
            lambda state_key: self._state_controller.apply_state_settings(state_key)
        )

        # ═════════════════════════════════════════════════════════════
        # UI → Business Logic (Upward calls - allowed)
        # ═════════════════════════════════════════════════════════════

        # State changes from StateController → CoreManager
        self._state_controller.state_changed.connect(
            self.core_manager.on_state_changed
        )

        # Window output signals → Business Logic
        self.window.tick_requested.connect(
            self.core_manager.process_movement_tick
        )
        self.window.bubble_toggle_requested.connect(
            self._on_bubble_toggle_requested
        )

    # ═════════════════════════════════════════════════════════════
    # Domain Event Translation Methods (Application Layer)
    # ═════════════════════════════════════════════════════════════

    def _on_chat_response_received(self, response_text: str, kwargs: dict):
        """Translate chat response domain event to UI bubble display."""
        self._bubble_controller.set_text(
            response_text,
            override_visibility=kwargs.get("override_visibility", False),
            auto_hide=kwargs.get("auto_hide", True),
            hide_delay_ms=kwargs.get("hide_delay_ms", 6000),
        )

    def _on_chat_operation_started(self):
        """Translate chat operation started domain event to UI busy cursor."""
        self.window.set_busy_cursor(True)

    def _on_chat_operation_completed(self):
        """Translate chat operation completed domain event to UI cursor reset."""
        self.window.set_busy_cursor(False)

    def _on_chat_error_occurred(self, error_message: str):
        """Translate chat error domain event to UI notification."""
        self._dialog_manager.show_notification(
            severity="error",
            title="聊天錯誤",
            message=error_message
        )

    def _on_domain_state_changed(self, state_key: str):
        """Translate state changed domain event to UI GIF loading."""
        self.window.current_state_key = state_key
        self._load_gif_for_state(state_key)

    def _on_domain_transition_completed(self, target_state_key: str):
        """Translate transition completed domain event to UI GIF loading."""
        self._on_domain_state_changed(target_state_key)

    def _load_gif_for_state(self, state_key: str):
        """Resolve GIF path for a state and load it via SpriteController."""
        gif_path = self._state_service.get_gif_path(state_key)
        if gif_path:
            self._sprite_controller.load_sprite(str(gif_path))

    def _on_bubble_toggle_requested(self, state_key: str, checked: bool):
        """Handle bubble toggle from UI — delegates to StateController + BubbleController."""
        if self._state_controller.toggle_bubble_visibility(state_key, checked):
            self._bubble_controller.set_visible(checked)

    def _connect_ui_controllers(self):
        """Connect UI controllers to Window and wire all UI-layer dependencies."""

        # ─────────────────────────────────────────────────────────
        # Create mouse event handler
        # ─────────────────────────────────────────────────────────
        mouse_handler = MouseEventHandler(
            click_threshold=CLICK_DRAG_THRESHOLD_PX,
        )

        # ─────────────────────────────────────────────────────────
        # Inject all controllers into Window via public API
        # ─────────────────────────────────────────────────────────
        self.window.inject_controllers(
            state_controller=self._state_controller,
            sprite_controller=self._sprite_controller,
            dialog_manager=self._dialog_manager,
            click_action_controller=self._click_action_controller,
            bubble_controller=self._bubble_controller,
            mouse_handler=mouse_handler,
        )

        # ─────────────────────────────────────────────────────────
        # Chat UI helper (owns core_manager + bubble_controller refs)
        # ─────────────────────────────────────────────────────────
        chat_ui = ChatUIHelper(
            window=self.window,
            core_manager=self.core_manager,
            bubble_controller=self._bubble_controller,
        )

        # ─────────────────────────────────────────────────────────
        # Context-menu controller (assembles snapshot/callbacks)
        # ─────────────────────────────────────────────────────────
        context_menu_ctrl = ContextMenuController(
            window=self.window,
            state_service=self._state_service,
            state_controller=self._state_controller,
            dialog_manager=self._dialog_manager,
            bubble_controller=self._bubble_controller,
            core_manager=self.core_manager,
            chat_ui=chat_ui,
            default_idle_gif=STATE_DIR / "idle.gif",
        )
        self.window.context_menu_requested.connect(context_menu_ctrl.show)
        # prevent GC of controller while window is alive
        self._context_menu_ctrl = context_menu_ctrl

        # ─────────────────────────────────────────────────────────
        # Wire mouse event handler signals
        # ─────────────────────────────────────────────────────────
        mouse_handler.window_drag_requested.connect(self.window.move)
        mouse_handler.drag_started.connect(self._on_doro_dragged)
        mouse_handler.click_detected.connect(
            lambda: (
                self.window.mark_user_activity(),
                self._click_action_controller.trigger_random_action(),
            )
        )
        mouse_handler.user_activity_detected.connect(
            self.window.mark_user_activity
        )
        mouse_handler.user_activity_detected.connect(self._idle_behavior.reset)

        # ─────────────────────────────────────────────────────────
        # Connect UI controller signals → Window
        # ─────────────────────────────────────────────────────────
        self._state_controller.repaint_requested.connect(self.window.update)
        self._state_controller.state_list_updated.connect(
            self.window.on_state_list_updated
        )

        self._sprite_controller.repaint_requested.connect(self.window.update)
        self._sprite_controller.sprite_renderer_changed.connect(
            self.window.on_sprite_renderer_changed
        )
        self._sprite_controller.sprite_size_changed.connect(
            lambda _: self.window.on_sprite_renderer_changed()
        )

        # ─────────────────────────────────────────────────────────
        # Apply persisted bubble configuration
        # ─────────────────────────────────────────────────────────
        self._bubble_controller.apply_persisted_config(
            BubbleConfig(
                offset_x=self._config_manager.ui.bubble_offset_x,
                offset_y=self._config_manager.ui.bubble_offset_y,
                scale=self._config_manager.ui.bubble_scale,
                auto_hide_ms=BUBBLE_AUTO_HIDE_MS,
            )
        )

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()

    # ═════════════════════════════════════════════════════════════════
    # Chat context injection (Phase 1c hotfix)
    # ═════════════════════════════════════════════════════════════════

    def _build_doro_state_text(self) -> str:
        """Compose the ``[Doro 當下狀態]`` block injected before each chat turn.

        Three sampled facts the LLM needs to choose a sensible
        ``[MOVE:to;...]`` target: Doro's foot position (the same anchor
        ``[MOVE:to;x;y]`` walks to and ``[mouse:click]`` fires at — kept in
        physical pixels so the LLM's arithmetic on a11y element coordinates
        works out), the screen size in those same physical pixels, and the
        class string of the foreground window under Doro's feet.
        """
        from .core.automation import window_class

        # Reuse the live automation adapter when it exists so the LLM-facing
        # foot matches exactly what `_fire_now` will sample. (Adapter lazily
        # routes through `DoroWindow.sprite_foot_offset_logical` and the
        # DPR helper.) Construct an ephemeral one when automation isn't
        # wired — the LLM still benefits from a consistent number.
        try:
            adapter = _QtAutomationWindowAdapter(self.window)
            fx, fy = adapter.foot_position_physical()
        except Exception:
            return ""

        # Match the click path: full screen geometry × dpr, not the
        # work-area `availableGeometry`. The LLM's coordinate space must
        # equal what `_fire_now` clamps against, otherwise a target near
        # the taskbar can be rejected after passing LLM-side validation.
        sw, sh = 0, 0
        try:
            screen = self.window.screen()
            if screen is not None:
                geo = screen.geometry()
                dpr = screen.devicePixelRatio() or 1.0
                sw = int(geo.width() * dpr)
                sh = int(geo.height() * dpr)
        except Exception:
            pass

        # `window_class.read_at` calls Win32 `WindowFromPoint`/
        # `ChildWindowFromPointEx` — without setting Doro to mouse-
        # transparent first, the topmost window at the foot is Doro
        # itself, so the LLM sees "前景視窗 class: Doro" and can't
        # plan a click on anything else.
        class_name = "unknown"
        try:
            adapter.set_mouse_transparent(True)
            try:
                read = window_class.read_at(fx, fy)
            finally:
                adapter.set_mouse_transparent(False)
            if read:
                class_name = read
        except Exception:
            pass

        if not sw or not sh:
            screen_line = "螢幕: 未知"
        else:
            screen_line = f"螢幕: {sw}×{sh}"

        return (
            "[Doro 當下狀態]\n"
            f"腳底位置: x={fx}, y={fy}\n"
            f"{screen_line}\n"
            f"前景視窗 class: {class_name}"
        )

    # ═════════════════════════════════════════════════════════════════
    # Automation (Phase 1c) construction
    # ═════════════════════════════════════════════════════════════════

    def _maybe_build_automation(self) -> "AutomationManager | None":
        """Build the AutomationManager whenever pynput is importable.

        The manager self-gates on ``automation.mouse_enabled`` at every
        ``execute_click`` (early-returns DISABLED), so building it
        unconditionally lets the settings toggle take effect at runtime
        with no restart while costing nothing when disabled — the gate
        short-circuits before any synthetic event fires.

        Returns None on import / backend init failure — Doro still
        works fine without automation.
        """
        try:
            from .core.automation.backend_pynput import PynputBackend
        except Exception as exc:  # pragma: no cover - import-time path
            logger.warning(
                f"pynput not installed; mouse-click automation unavailable — "
                f"install with `pip install pynput` ({exc})"
            )
            return None

        try:
            backend = PynputBackend()
        except Exception as exc:  # pragma: no cover - runtime path
            logger.warning(
                f"pynput backend init failed; mouse-click automation "
                f"unavailable ({exc})"
            )
            return None

        window_port = _QtAutomationWindowAdapter(self.window)

        from PySide6 import QtCore as _QtCore

        def _schedule(ms: int, fn) -> None:
            _QtCore.QTimer.singleShot(int(ms), fn)

        # Esc fires from pynput's listener thread; this bridge marshals
        # the callback onto the Qt main thread before any Qt-bound work
        # (state flips, QSettings writes, dispatcher cancellation) runs.
        # Held on self so the QObject isn't GC'd while the manager keeps
        # the emit method as its `marshal` callable.
        self._esc_main_thread_bridge = _MainThreadBridge()

        # Reuse the existing transition lock — wrapping the StateService
        # begin/end calls so IdleBehaviorManager (which already respects
        # `state_service.is_transitioning()`) won't preempt the wind-up.
        coord = _TransitionCoordinatorAdapter(self._state_service)
        animator = _QtWindUpAnimatorAdapter(
            self._state_service,
            self._action_service.click_state_key,
        )

        from .ui.click_warning_overlay import ClickWarningOverlay

        # Widget stays alive through the adapter → manager → DoroApp chain.
        overlay_adapter = _QtClickWarningOverlayAdapter(
            ClickWarningOverlay(), self.window
        )

        # Cursor-free click backend. Production uses UIA's InvokePattern
        # via the already-built A11yService; on non-Windows (where the
        # service runs against the NullA11yBackend) the clicker returns
        # False and clicks surface as NOT_INVOCABLE rather than moving
        # the user's cursor.
        from .core.a11y import A11yClickerAdapter, NullA11yClicker
        import sys as _sys
        if _sys.platform == "win32" and self._a11y is not None:
            a11y_clicker = A11yClickerAdapter(self._a11y)
        else:
            a11y_clicker = NullA11yClicker()

        manager = AutomationManager(
            config_manager=self._config_manager,
            window=window_port,
            input_backend=backend,
            transition_coordinator=coord,
            wind_up_animator=animator,
            warning_overlay=overlay_adapter,
            bounds_provider=self._click_target_bounds,
            click_target_provider=self._movement.take_last_target_physical,
            a11y_clicker=a11y_clicker,
            on_esc_extra=self._cancel_dispatcher_on_esc,
            schedule=_schedule,
            marshal=self._esc_main_thread_bridge.fired.emit,
        )
        return manager

    def _on_doro_dragged(self) -> None:
        """User dragged Doro — kill any in-flight click, active movement,
        and queued click.

        Three layers can hold a "click is coming" promise; all three
        must be torn down or the click ends up at the post-drag foot:

        1. AutomationManager's wind-up timer (if a `[mouse:click]` was
           already in flight when the drag started). `cancel_pending_click`
           sets `_abort_pending=True` so the timer's expiry path finalises
           as ESC_ABORT instead of firing.
        2. The action dispatcher's current MovementAction
           (`MovementWaitPhase`). `cancel_current` runs `phase.cancel()`,
           which unsubscribes from MovementManager's completion listeners.
        3. Any queued ClickAction tail. `cancel_current` clears the
           queue, so the post-movement click doesn't get picked up.

        Order matters for #2 vs the subsequent `cancel_active_movement`:
        dispatcher cancel runs first so when MovementManager fires its
        listeners during shutdown, no one is subscribed any more — that
        prevents the cancelled action from being inadvertently advanced.
        """
        if self._automation is not None:
            self._automation.cancel_pending_click("drag")
        dispatcher = getattr(self, "_action_dispatcher", None)
        if dispatcher is not None:
            dispatcher.cancel_current("drag")
        self._movement.cancel_active_movement()

    def _on_about_to_quit(self) -> None:
        """Tear down background workers so the process can exit cleanly.

        AutomationManager owns the pynput listener thread; A11yService
        owns the UIA worker pool; ForegroundTracker owns its own poll
        timer. Without these calls, a hung UIA read can pin the process
        until the OS reaps it.
        """
        from .utils.logger import get_logger as _gl
        logger = _gl(__name__)
        # (subsystem, attribute-on-self, method-name-on-subsystem)
        shutters = [
            ("automation", "_automation", "shutdown"),
            ("a11y", "_a11y", "shutdown"),
            ("foreground_tracker", "_fg_tracker", "stop"),
        ]
        for label, attr, method in shutters:
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            stop = getattr(obj, method, None)
            if not callable(stop):
                continue
            try:
                stop()
            except Exception:  # pragma: no cover - shutdown is best-effort
                logger.exception(f"{label} shutdown raised")

    def _cancel_dispatcher_on_esc(self) -> None:
        """Forward Esc to the ActionDispatcher so any queued click or
        in-flight movement waiter unwinds. Called by AutomationManager's
        Esc listener; safe before the dispatcher is constructed (no-op).
        AutomationManager's own click-abort handling runs first, so an
        in-flight click is already cancelled by the time we get here —
        this hook is what cleans up the *next* queued action."""
        dispatcher = getattr(self, "_action_dispatcher", None)
        if dispatcher is not None:
            dispatcher.cancel_current("esc")

    def _click_target_bounds(self):
        """Bounds (physical px) of the a11y element under the latest
        ``[move:to;x=;y=]`` target — what the click warning overlay frames
        during the 1.5s wind-up. ``None`` if no a11y read or no recent
        target.

        The three "no bounds" branches each print a distinct reason so
        a missing red frame is diagnosable from stdout without rebuilding.
        """
        if self._a11y is None:
            print("[doro click] warning-frame: a11y service unavailable", flush=True)
            return None
        target = self._movement.last_target_physical
        if target is None:
            print("[doro click] warning-frame: no recent [MOVE:to] target", flush=True)
            return None
        bounds = self._a11y.bounds_at_physical_point(*target)
        if bounds is None:
            print(
                f"[doro click] warning-frame: no a11y element at "
                f"target={target} in _last_elements",
                flush=True,
            )
        return bounds

    # ═════════════════════════════════════════════════════════════════
    # A11y tree reader (Phase 1d) construction
    # ═════════════════════════════════════════════════════════════════

    def _maybe_build_a11y(self):
        """Build the A11yService whenever the platform backend can be set up.

        The service self-gates on ``automation.a11y_enabled`` at every read, so
        building it unconditionally lets the settings toggle take effect at
        runtime (no restart) while costing nothing when disabled — the read
        short-circuits before importing the backend or spawning threads. On any
        setup failure returns None — chat still works without it.
        """
        import sys

        try:
            from .core.a11y.service import A11yService
            if sys.platform == "win32":
                from .core.a11y.backend_uiautomation import UIAutomationBackend
                backend = UIAutomationBackend()
            else:
                from .core.a11y.backend_null import NullA11yBackend
                backend = NullA11yBackend()
            return A11yService(
                config_manager=self._config_manager,
                backend=backend,
                handle_provider=self._fg_tracker.handle,
            )
        except Exception as exc:  # pragma: no cover - import/setup path
            from .utils.logger import get_logger as _gl
            _gl(__name__).warning(f"A11y setup failed: {exc}")
            return None


class _QtWindUpAnimatorAdapter:
    """Drive the click wind-up animation by swapping the visible state.

    The :class:`ActionService` registered ``click_action`` as a hidden
    protected state with the appropriate ``gif_id`` (user-bound or
    fallback) at bootstrap. During wind-up we ``set_state`` to it with
    ``force=True`` (the transition lock is already engaged), record the
    previous state, and restore on end. Restoration uses ``force=True``
    too because the lock is still held until AutomationManager finalizes.
    """

    def __init__(self, state_service, click_state_key: str) -> None:
        self._state_service = state_service
        self._click_state_key = click_state_key
        self._prev_state_key: Optional[str] = None

    def begin(self) -> None:
        self._prev_state_key = self._state_service.get_current_state_key()
        if not self._state_service.set_state(self._click_state_key, force=True):
            # State not registered or set_state refused — drop the saved key
            # so end() doesn't try to flip back from a state we never left.
            self._prev_state_key = None

    def end(self) -> None:
        if self._prev_state_key is None:
            return
        self._state_service.set_state(self._prev_state_key, force=True)
        self._prev_state_key = None


class _MainThreadBridge(QtCore.QObject):
    """Cross-thread trampoline for callbacks that must run on the main thread.

    ``fired.emit(fn)`` from any thread; ``fn()`` then runs on the thread
    this QObject lives on (the main thread, because the bridge is
    constructed there). Qt's auto-connection delivers the signal queued
    when the emitting thread differs from the receiving thread, which
    is exactly the marshalling guarantee the Esc callback needs.
    """

    fired = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.fired.connect(lambda fn: fn())


class _QtClickWarningOverlayAdapter:
    """Adapter exposing a :class:`ClickWarningOverlay` widget as a
    :class:`ClickWarningOverlayPort` for the AutomationManager.

    ``begin(None)`` is a no-op so the manager can call us unconditionally
    even when there's no a11y element at the click target.
    """

    def __init__(self, overlay, host_window) -> None:
        self._overlay = overlay
        self._host = host_window

    def begin(self, bounds_physical) -> None:
        if bounds_physical is None:
            # Surface this to stdout (not just logger.debug, which is
            # silent under the default INFO level) so a missing red
            # frame doesn't look like the overlay was removed when
            # bounds_at_physical_point actually just returned None.
            print(
                "[doro click] warning-frame skipped: bounds=None "
                "(no a11y element at the move target — _last_elements "
                "may be stale or from a different window)",
                flush=True,
            )
            return
        print(
            f"[doro click] warning-frame begin: bounds={bounds_physical}",
            flush=True,
        )
        self._overlay.set_bounds_and_show(bounds_physical, self._host)

    def end(self) -> None:
        print("[doro click] warning-frame end", flush=True)
        self._overlay.hide_and_clear()


class _TransitionCoordinatorAdapter:
    """Adapter giving AutomationManager `begin()` / `end()` over StateService."""

    def __init__(self, state_service) -> None:
        self._state_service = state_service

    def begin(self) -> bool:
        return self._state_service.begin_transition()

    def end(self) -> bool:
        return self._state_service.end_transition()


class _QtAutomationWindowAdapter:
    """Adapter exposing the live DoroWindow as an :class:`AutomationWindowPort`."""

    def __init__(self, window) -> None:
        self._window = window

    def foot_position_logical(self) -> tuple[int, int]:
        # Sprite's visual foot, not frame.bottom() — see
        # `DoroWindow.sprite_foot_offset_logical` for why.
        top_left = self._window.frameGeometry().topLeft()
        offset = self._window.sprite_foot_offset_logical()
        return (top_left.x() + offset.x(), top_left.y() + offset.y())

    def foot_position_physical(self) -> tuple[int, int]:
        from PySide6 import QtCore as _QtCore
        from PySide6 import QtGui as _QtGui

        from .core.automation.coordinates import compute_physical_pixel_at

        fx, fy = self.foot_position_logical()
        screen = (
            _QtGui.QGuiApplication.screenAt(_QtCore.QPoint(fx, fy))
            or self._window.screen()
        )
        if screen is None:
            return (fx, fy)
        geom = screen.geometry()
        return compute_physical_pixel_at(
            (fx, fy),
            screen_origin_logical=(geom.x(), geom.y()),
            device_pixel_ratio=screen.devicePixelRatio(),
        )

    def set_mouse_transparent(self, transparent: bool) -> None:
        """Make Doro's window invisible to mouse hit-testing during a
        sample.

        Qt's `WA_TransparentForMouseEvents` only filters mouse events
        inside Qt — it does NOT make Win32 `WindowFromPoint` skip the
        window, which is what `read_window_class_at` actually calls.
        Without the Win32-level flag the click pipeline self-clicks
        whenever Doro's window overlaps the target (which is the common
        case after `[move:to;...]` lands Doro's foot exactly on the
        click coordinate).

        On Windows we toggle `WS_EX_TRANSPARENT` (the actual mechanism
        `WindowFromPoint` honours). On other platforms we fall back to
        the Qt attribute alone, which is fine because non-Windows
        platforms don't go through this self-click path.
        """
        from PySide6 import QtCore as _QtCore

        try:
            self._window.setAttribute(
                _QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, bool(transparent)
            )
        except Exception:  # pragma: no cover - defensive
            pass

        import sys
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self._window.winId())
            if hwnd == 0:
                return
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            user32 = ctypes.windll.user32
            # GetWindowLongW returns LONG (32-bit signed). On 64-bit
            # Windows the extended style fits in a LONG; using the W
            # variant matches Qt's own usage and avoids the LongPtr
            # API surface we don't need here.
            current = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if bool(transparent):
                new = current | WS_EX_TRANSPARENT
            else:
                new = current & ~WS_EX_TRANSPARENT
            if new != current:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
        except Exception:  # pragma: no cover - defensive
            from .utils.logger import get_logger as _gl
            _gl(__name__).exception("WS_EX_TRANSPARENT toggle failed")

    def screen_size_logical(self) -> tuple[int, int]:
        try:
            screen = self._window.screen()
            if screen is None:
                return (1920, 1080)
            size = screen.availableGeometry().size()
            return (size.width(), size.height())
        except Exception:  # pragma: no cover - defensive
            return (1920, 1080)

    def screen_size_physical(self) -> tuple[int, int]:
        l, t, w, h = self.screen_geometry_physical()
        return (w, h)

    def screen_geometry_physical(self) -> tuple[int, int, int, int]:
        try:
            screen = self._window.screen()
            if screen is None:
                return (0, 0, 1920, 1080)
            geo = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            return (
                int(geo.x() * dpr),
                int(geo.y() * dpr),
                int(geo.width() * dpr),
                int(geo.height() * dpr),
            )
        except Exception:  # pragma: no cover - defensive
            return (0, 0, 1920, 1080)

    def device_pixel_ratio(self) -> float:
        try:
            screen = self._window.screen()
            if screen is None:
                return 1.0
            return float(screen.devicePixelRatio() or 1.0)
        except Exception:  # pragma: no cover - defensive
            return 1.0
