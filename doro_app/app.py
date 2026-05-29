"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from typing import Optional

from .bootstrap import BootstrappedDependencies, bootstrap_environment
from .constants import (
    BUBBLE_AUTO_HIDE_MS,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    BUBBLE_DEFAULT_SCALE,
    CLICK_DRAG_THRESHOLD_PX,
)
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
from .utils.paths import COMPANION_PROMPTS_PATH, STATE_DIR


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
        self._movement_repo = deps.movement_repo
        self._movement = MovementManager(
            window=self.window,
            state_service=self._state_service,
            movement_repo=self._movement_repo,
        )

        # ═════════════════════════════════════════════════════════════
        # Phase 4: Create ChatController (needs StateController + MovementManager)
        # ═════════════════════════════════════════════════════════════

        # ─── A11y tree reader (Phase 1d) ─────────────────────────
        # Optional: only constructed if a11y_enabled. Independent of mouse
        # clicking — the user may grant "see the window" without "click it".
        self._a11y = self._maybe_build_a11y()

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

        self._chat_orchestrator = ChatOrchestrator(
            self._chat_controller,
            self._movement,
            self._state_service,
            automation=self._automation,
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
        # Under Live2D mode the model is persistent — skip sprite reloading.
        if self._sprite_controller.renderer_type == "live2d":
            return
        self._load_gif_for_state(state_key)

    def _on_domain_transition_completed(self, target_state_key: str):
        """Translate transition completed domain event to UI GIF loading."""
        self._on_domain_state_changed(target_state_key)

    def _load_gif_for_state(self, state_key: str):
        """Resolve GIF path for a state and load it via SpriteController."""
        gif_path = self._state_service.get_gif_path(state_key)
        if gif_path:
            self._sprite_controller.load_sprite(str(gif_path))

    def _on_live2d_unavailable(self):
        """Notify the user via bubble that live2d-py is not installed."""
        self._bubble_controller.set_text(
            "需要安裝 live2d-py 才能使用 Live2D 模型喔！\n"
            "pip install live2d-py",
            auto_hide=True,
            hide_delay_ms=8000,
        )

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
            reload_sprite=self._load_gif_for_state,
        )
        self.window.context_menu_requested.connect(context_menu_ctrl.show)
        # prevent GC of controller while window is alive
        self._context_menu_ctrl = context_menu_ctrl

        # ─────────────────────────────────────────────────────────
        # Wire mouse event handler signals
        # ─────────────────────────────────────────────────────────
        mouse_handler.window_drag_requested.connect(self.window.move)
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
        self._sprite_controller.live2d_unavailable.connect(
            self._on_live2d_unavailable
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
        ``[MOVE:to;...]`` target: Doro's current logical position, the
        screen size, and the class string of the foreground window under
        Doro's feet. Each sub-step is defensive so partial info still
        reaches the LLM if e.g. the X server is missing.
        """
        try:
            frame = self.window.frameGeometry()
            cx = int(frame.center().x())
            cy = int(frame.center().y())
        except Exception:
            return ""

        sw, sh = 1920, 1080
        try:
            screen = self.window.screen()
            if screen is not None:
                size = screen.availableGeometry().size()
                sw, sh = size.width(), size.height()
        except Exception:
            pass

        class_name = "unknown"
        try:
            from .core.automation.coordinates import compute_physical_pixel_for_qt_window
            from .core.automation import window_class

            phys = compute_physical_pixel_for_qt_window(self.window)
            if phys is not None:
                read = window_class.read_at(phys[0], phys[1])
                if read:
                    class_name = read
        except Exception:
            pass

        return (
            "[Doro 當下狀態]\n"
            f"位置: x={cx}, y={cy}\n"
            f"螢幕: {sw}×{sh}\n"
            f"前景視窗 class: {class_name}"
        )

    # ═════════════════════════════════════════════════════════════════
    # Automation (Phase 1c) construction
    # ═════════════════════════════════════════════════════════════════

    def _maybe_build_automation(self) -> "AutomationManager | None":
        """Build the AutomationManager only if automation.mouse_enabled is True
        in config (or DORO_MOUSE=true at startup). Returns None on any setup
        failure — Doro still works fine without automation.
        """
        if not self._config_manager.automation.mouse_enabled:
            return None

        try:
            from .core.automation.backend_pynput import PynputBackend
        except Exception as exc:  # pragma: no cover - import-time path
            from .utils.logger import get_logger as _gl
            _gl(__name__).warning(f"Automation requested but pynput unavailable: {exc}")
            return None

        try:
            backend = PynputBackend()
        except Exception as exc:  # pragma: no cover - runtime path
            from .utils.logger import get_logger as _gl
            _gl(__name__).warning(f"Automation backend init failed: {exc}")
            return None

        window_port = _QtAutomationWindowAdapter(self.window)

        from PySide6 import QtCore as _QtCore

        def _schedule(ms: int, fn) -> None:
            _QtCore.QTimer.singleShot(int(ms), fn)

        # Reuse the existing transition lock — wrapping the StateService
        # begin/end calls so IdleBehaviorManager (which already respects
        # `state_service.is_transitioning()`) won't preempt the wind-up.
        coord = _TransitionCoordinatorAdapter(self._state_service)
        animator = _QtWindUpAnimatorAdapter(
            self._state_service,
            self._action_service.click_state_key,
        )

        manager = AutomationManager(
            config_manager=self._config_manager,
            window=window_port,
            input_backend=backend,
            transition_coordinator=coord,
            wind_up_animator=animator,
            schedule=_schedule,
        )
        return manager

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
            return A11yService(config_manager=self._config_manager, backend=backend)
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
        frame = self._window.frameGeometry()
        return (frame.center().x(), frame.bottom() - 1)

    def foot_position_physical(self) -> tuple[int, int]:
        from .core.automation.coordinates import compute_physical_pixel_for_qt_window

        result = compute_physical_pixel_for_qt_window(self._window)
        if result is not None:
            return result
        # Fallback: assume DPR=1 (better than crashing).
        return self.foot_position_logical()

    def set_mouse_transparent(self, transparent: bool) -> None:
        from PySide6 import QtCore as _QtCore

        try:
            self._window.setAttribute(
                _QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, bool(transparent)
            )
        except Exception:  # pragma: no cover - defensive
            pass

    def screen_size_logical(self) -> tuple[int, int]:
        try:
            screen = self._window.screen()
            if screen is None:
                return (1920, 1080)
            size = screen.availableGeometry().size()
            return (size.width(), size.height())
        except Exception:  # pragma: no cover - defensive
            return (1920, 1080)
