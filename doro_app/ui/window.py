"""Main application window and UI logic for Doro."""

from __future__ import annotations

import time
from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    TIMER_INTERVAL_MS,
    WINDOW_INITIAL_WIDTH,
    WINDOW_INITIAL_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    SPRITE_DEFAULT_WIDTH,
    SPRITE_DEFAULT_HEIGHT,
    SPRITE_OFFSET_X,
    PANEL_DEFAULT_WIDTH_HINT,
    PANEL_DEFAULT_HEIGHT_HINT,
    BUBBLE_DEFAULT_OFFSET_X,
    BUBBLE_DEFAULT_OFFSET_Y,
    DEFAULT_MOVE_STATE_KEY,
    WINDOW_INITIAL_POSITION_OFFSET_X,
    WINDOW_INITIAL_POSITION_OFFSET_Y,
)
from .components.bubble_controller import BubbleController
from .rendering.design_tokens import tokens
from .rendering.gif_sprite_renderer import GifSpriteRenderer
from .rendering.sprite_renderer import SpriteRenderer
from .rendering.rendering_engine import RenderingEngine
from .events.mouse_event_handler import MouseEventHandler
from .layout.layout_manager import WindowLayoutManager
from .viewmodels.doro_viewmodel import DoroViewModel
from ..utils.logger import get_logger
from ..core.state import StateService
from .theme.theme import ensure_application_theme
from ..utils.config_manager import ConfigManager

logger = get_logger(__name__)


class DoroWindow(QtWidgets.QWidget):
    # Output signals (decoupling UI from business logic)
    tick_requested = QtCore.Signal(float)  # dt
    bubble_toggle_requested = QtCore.Signal(str, bool)  # state_key, checked
    context_menu_requested = QtCore.Signal(QtCore.QPoint)  # global_pos

    def __init__(
        self,
        state_service: StateService,
        not_topmost: bool = False,
        config_manager: ConfigManager | None = None,
    ):
        """
        Initialize the Doro window (UI layer only).

        Args:
            state_service: State management service (injected)
            not_topmost: If True, window will not stay on top
            config_manager: ConfigManager for type-safe config access

        Note:
            Controllers and event handlers are wired after construction
            by DoroApp via inject_controllers().
        """
        super().__init__()
        logger.info("Initializing Doro window")
        ensure_application_theme()

        # ─────────────────────────────────────────────────────────
        # Qt Widget Setup
        # ─────────────────────────────────────────────────────────
        self.resize(WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool  # hides from taskbar
        )
        if not not_topmost:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # ─────────────────────────────────────────────────────────
        # Injected Dependencies
        # ─────────────────────────────────────────────────────────
        self._state_service = state_service
        self._config_manager = config_manager

        # ─────────────────────────────────────────────────────────
        # Dependencies wired later (due to circular dependency)
        # ─────────────────────────────────────────────────────────
        # Controllers
        self._state_controller = None
        self._sprite_controller = None
        self._dialog_manager = None
        self._click_action_controller = None
        # Managers
        self._bubble_controller: BubbleController | None = None
        # Event handlers
        self._mouse_handler: MouseEventHandler | None = None

        # ─────────────────────────────────────────────────────────
        # ViewModel (Presentation State)
        # ─────────────────────────────────────────────────────────
        self._view_model = DoroViewModel()
        self._view_model.set_sprite_size(QtCore.QSize(SPRITE_DEFAULT_WIDTH, SPRITE_DEFAULT_HEIGHT))
        self._view_model.set_sprite_offset_x(SPRITE_OFFSET_X)

        # ─────────────────────────────────────────────────────────
        # Rendering Engine
        # ─────────────────────────────────────────────────────────
        self._rendering_engine = RenderingEngine(self._view_model)

        # ─────────────────────────────────────────────────────────
        # Animation Timer
        # ─────────────────────────────────────────────────────────
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        # NOTE: timer is started in inject_controllers() after all dependencies are wired

        # ─────────────────────────────────────────────────────────
        # UI State Variables
        # ─────────────────────────────────────────────────────────
        self._current_state_key: str = ""
        self._state_list_text: str = ""

        self._sprite_renderer: SpriteRenderer = GifSpriteRenderer(self._view_model)

        self._last_user_activity = time.monotonic()

        self._panel_width_hint = PANEL_DEFAULT_WIDTH_HINT
        self._panel_height_hint = PANEL_DEFAULT_HEIGHT_HINT
        self._panel_rect_cache: QtCore.QRectF | None = None
        self._sprite_anchor_top: float | None = None
        # Which side of the sprite the bubble is reserved on. Decided from the
        # sprite's on-screen position each time the bubble resizes: when Doro is
        # near the bottom of the screen the bubble flips above so it never has
        # to push the sprite up or cover it. False = below (the normal case).
        self._bubble_above: bool = False

        self._default_move_state_key = DEFAULT_MOVE_STATE_KEY
        self._sizing_in_progress = False
        self._last_tick_time = time.monotonic()

        self._chat_cursor_overridden = False

        # ─────────────────────────────────────────────────────────
        # Apply UI Preferences from Config
        # ─────────────────────────────────────────────────────────
        self.apply_window_preferred_size()

        # ─────────────────────────────────────────────────────────
        # Context Menu and Window Positioning
        # ─────────────────────────────────────────────────────────
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        # Place near bottom-right of primary screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(
                g.right() - self.width() - WINDOW_INITIAL_POSITION_OFFSET_X,
                g.bottom() - self.height() - WINDOW_INITIAL_POSITION_OFFSET_Y,
            )

        self.setWindowTitle("doro")

    # ═══════════════════════════════════════════════════════════
    # Public Properties
    # ═══════════════════════════════════════════════════════════

    @property
    def view_model(self):
        """Get ViewModel (needed by controllers)."""
        return self._view_model

    @property
    def state_list_text(self) -> str:
        """Get current state list text (used by ChatController)."""
        return self._state_list_text or ""

    @property
    def current_state_key(self) -> str:
        """Get current state key."""
        return self._current_state_key

    @current_state_key.setter
    def current_state_key(self, value: str):
        self._current_state_key = value

    @property
    def sprite_renderer(self) -> SpriteRenderer:
        """Active sprite renderer (used by ContextMenuController for avatar)."""
        return self._sprite_renderer

    # ═══════════════════════════════════════════════════════════
    # Controller Injection
    # ═══════════════════════════════════════════════════════════

    def inject_controllers(
        self,
        *,
        state_controller,
        sprite_controller,
        dialog_manager,
        click_action_controller,
        bubble_controller,
        mouse_handler,
    ):
        """Wire controllers into the window (called once by DoroApp after construction)."""
        self._state_controller = state_controller
        self._sprite_controller = sprite_controller
        self._dialog_manager = dialog_manager
        self._click_action_controller = click_action_controller
        self._bubble_controller = bubble_controller
        self._mouse_handler = mouse_handler
        # Share the renderer owned by the sprite controller
        self._sprite_renderer = sprite_controller.renderer
        # All dependencies wired — safe to start the animation timer
        self._timer.start(TIMER_INTERVAL_MS)

    # ─────────────────────────────────────────────────────────
    # Controller signal handlers
    # ─────────────────────────────────────────────────────────

    def on_state_list_updated(self, state_list_text: str):
        """Handle state list update from StateController."""
        self._state_list_text = state_list_text

    def on_sprite_renderer_changed(self):
        """Handle sprite renderer content update from SpriteController."""
        if self._sprite_controller:
            self._sprite_renderer = self._sprite_controller.renderer
        self.apply_window_preferred_size()
        self.update()

    # --- Animation -------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        dt = now - getattr(self, "_last_tick_time", now)
        self._last_tick_time = now
        if dt < 0.0:
            dt = 0.0
        dt = min(dt, tokens.animation.max_delta_time)

        # Signal business layer to process movement
        self.tick_requested.emit(dt)

        # Advance the active sprite renderer (per-frame hook for time-driven renderers)
        if self._sprite_controller:
            self._sprite_controller.tick(dt)

        # Use ViewModel for animation time
        self._view_model.tick(dt)
        self.update()

    # --- Interaction -----------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if self._mouse_handler is None:
            return super().mousePressEvent(e)
        if self._mouse_handler.handle_press(e, self.frameGeometry()):
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._mouse_handler is None:
            return super().mouseMoveEvent(e)
        if self._mouse_handler.handle_move(e):
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if self._mouse_handler is None:
            return super().mouseReleaseEvent(e)
        handled, _was_click = self._mouse_handler.handle_release(e)
        if handled:
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def leaveEvent(self, e: QtCore.QEvent):
        if self._mouse_handler is None:
            return super().leaveEvent(e)
        self._mouse_handler.handle_leave()
        super().leaveEvent(e)

    def event(self, e: QtCore.QEvent):
        # A lost mouse grab (e.g. deactivation) may have no release event.
        if e.type() in (
            QtCore.QEvent.Type.UngrabMouse,
            QtCore.QEvent.Type.WindowDeactivate,
            QtCore.QEvent.Type.Hide,
        ):
            handler = getattr(self, "_mouse_handler", None)
            if handler is not None:
                handler.reset()
        return super().event(e)

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        self.mark_user_activity()
        super().keyPressEvent(e)

    def mark_user_activity(self):
        self._last_user_activity = time.monotonic()

    def seconds_since_last_activity(self) -> float:
        return time.monotonic() - self._last_user_activity

    def update_bubble_side_from_offset(self):
        """Update bubble side based on offset (called by BubbleController)."""
        self._view_model.set_bubble_side("center")

    def _available_screen_geometry(self) -> QtCore.QRect:
        """Get available screen geometry. Delegates to WindowLayoutManager."""
        return WindowLayoutManager.get_available_screen_geometry(self)

    def _clamp_window_position(self, desired: QtCore.QPoint) -> QtCore.QPoint:
        """Clamp window position to screen bounds. Delegates to WindowLayoutManager."""
        window_size = self.frameGeometry().size()
        screen_rect = self._available_screen_geometry()
        return WindowLayoutManager.clamp_position(desired, window_size, screen_rect)

    def _move_window_to(self, point: QtCore.QPoint):
        """Move window to position. Delegates to WindowLayoutManager."""
        WindowLayoutManager.move_window_safely(self, point)

    def _compute_panel_size_hint(self) -> tuple[float, float]:
        """Compute panel size hint. Delegates to WindowLayoutManager."""
        bubble_text = self._bubble_controller.text if self._bubble_controller else ""
        return WindowLayoutManager.compute_panel_size_hint(
            self._view_model.sprite_size,
            bubble_text,
        )

    def apply_window_preferred_size(self):
        """Apply preferred window size. Delegates to WindowLayoutManager.

        When the bubble has no text and isn't being force-shown, request a
        compact (sprite-sized) window so the visible sprite aligns with the
        window edges — keeps Doro's drawn position consistent with
        ``[MOVE:to]`` target arithmetic (which treats the window's bottom
        centre as the foot anchor).
        """
        panel_w_hint, panel_h_hint = self._compute_panel_size_hint()
        self._panel_width_hint = panel_w_hint
        self._panel_height_hint = panel_h_hint

        compact = self._should_collapse_to_sprite()

        # Visual continuity: in normal mode the sprite renders at the
        # (margin + offset)-driven position inside the window; in compact
        # mode it fills the window. Resizing without compensating moves
        # the sprite on screen — adjust the top-left so the sprite stays
        # put across the mode switch.
        sprite_center_screen = self._sprite_center_in_screen_coords()

        # Pick the side the bubble sits on BEFORE resizing, from where the
        # sprite currently is on screen. Near the bottom → flip above.
        if sprite_center_screen is not None:
            self._bubble_above = self._decide_bubble_above(sprite_center_screen, panel_h_hint)

        self._sizing_in_progress = True
        try:
            WindowLayoutManager.apply_window_preferred_size(
                self,
                self._view_model.sprite_size,
                panel_w_hint,
                panel_h_hint,
                compact=compact,
            )
            if sprite_center_screen is not None:
                self._reposition_to_keep_sprite_center(sprite_center_screen)
        finally:
            self._sizing_in_progress = False

    def _should_collapse_to_sprite(self) -> bool:
        """True when no bubble text is showing — window can shrink to sprite size."""
        if self._bubble_controller is None:
            return False
        if self._bubble_controller.text_show_override:
            return False
        if not (self._bubble_controller.text or "").strip():
            return True
        # Bubble has text but `set_visible(False)` may have been called.
        return not self._view_model.bubble_visible

    def _sprite_center_in_screen_coords(self) -> QtCore.QPointF | None:
        """Sprite centre in screen logical pixels, or None if window not laid out yet."""
        try:
            top_left = self.frameGeometry().topLeft()
        except Exception:
            return None
        sprite_center, _ = self._rendering_engine.calculate_sprite_center(
            self.size(),
            self._sprite_anchor_top,
            self._panel_height_hint,
            reserve_above=self._bubble_above,
        )
        return QtCore.QPointF(
            top_left.x() + sprite_center.x(),
            top_left.y() + sprite_center.y(),
        )

    def _decide_bubble_above(
        self, sprite_center_screen: QtCore.QPointF, panel_height_hint: float
    ) -> bool:
        """Decide whether the bubble should sit above the sprite.

        Compares the room left below vs. above the sprite on the actual screen.
        Flip above only when below can't fit the bubble and above has more room —
        otherwise keep the normal below placement (avoids flip-flopping).
        """
        screen_rect = self._available_screen_geometry()
        half_h = float(self._view_model.sprite_size.height()) / 2.0
        gap = float(tokens.spacing.sprite_bubble_gap) + float(tokens.spacing.margin_bottom)

        sprite_bottom = sprite_center_screen.y() + half_h
        sprite_top = sprite_center_screen.y() - half_h
        room_below = screen_rect.bottom() - sprite_bottom
        room_above = sprite_top - screen_rect.top()

        needed = float(panel_height_hint) + gap
        return room_below < needed and room_above > room_below

    def _reposition_to_keep_sprite_center(self, target_screen_center: QtCore.QPointF) -> None:
        """After a resize, move the window so the sprite stays at the same
        screen position. Computes the sprite centre in the NEW (post-resize)
        window using the same layout helper rendering uses, then offsets
        top-left to keep that screen point invariant."""
        # Reset anchor so layout recomputes for the new window size.
        self._sprite_anchor_top = None
        new_local_center, new_anchor = self._rendering_engine.calculate_sprite_center(
            self.size(),
            self._sprite_anchor_top,
            self._panel_height_hint,
            reserve_above=self._bubble_above,
        )
        if new_anchor is not None:
            self._sprite_anchor_top = new_anchor
        new_top_left = QtCore.QPoint(
            int(round(target_screen_center.x() - new_local_center.x())),
            int(round(target_screen_center.y() - new_local_center.y())),
        )
        clamped = WindowLayoutManager.clamp_position(
            new_top_left, self.size(), self._available_screen_geometry()
        )
        self.move(clamped)

    def contextMenuEvent(self, e: QtGui.QContextMenuEvent):
        self.mark_user_activity()
        self.context_menu_requested.emit(e.globalPos())

    # --- Painting --------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Disable animations - no bob (floating) or scale (breathing) effects
        # NOTE: ViewModel can calculate these, but we keep animations disabled for now
        bob = 0.0
        scale = 1.0

        # Calculate sprite center using RenderingEngine
        sprite_center, new_anchor = self._rendering_engine.calculate_sprite_center(
            self.size(),
            self._sprite_anchor_top,
            self._panel_height_hint,
            reserve_above=self._bubble_above,
        )
        if new_anchor is not None:
            self._sprite_anchor_top = new_anchor

        # Render sprite using RenderingEngine + SpriteRenderer
        self._rendering_engine.render_sprite(p, self._sprite_renderer, sprite_center, bob, scale)

        # Render text panel using RenderingEngine
        bubble_text = self._bubble_controller.text if self._bubble_controller else ""
        panel_should_draw = (
            (
                self._view_model.bubble_visible
                or (self._bubble_controller and self._bubble_controller.text_show_override)
            )
            and self._view_model.bubble_alpha > 0
            and bool(bubble_text.strip())
        )
        if panel_should_draw:
            from ..constants import COLOR_ALPHA_MAX

            alpha = min(max(int(self._view_model.bubble_alpha), 0), COLOR_ALPHA_MAX)
            self._panel_rect_cache = self._rendering_engine.render_text_panel(
                p,
                bubble_text,
                alpha,
                sprite_center,
                self.size(),
                self._panel_height_hint,
                prefer_above=self._bubble_above,
            )
        else:
            self._panel_rect_cache = None

    # ═══════════════════════════════════════════════════════════
    # Public Movement API - Window Operations
    # ═══════════════════════════════════════════════════════════

    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint:
        """Clamp window position to stay on screen (public API)."""
        return self._clamp_window_position(pos)

    def current_position(self) -> QtCore.QPoint:
        """Get the current top-left position of the window (public API)."""
        return self.frameGeometry().topLeft()

    def move_window_to(self, pos: QtCore.QPoint):
        """Move window to position (public API)."""
        self._move_window_to(pos)

    def sprite_foot_offset_logical(self) -> QtCore.QPoint:
        """Offset of the sprite's visual foot (bottom-centre) from the
        window's top-left, in Qt logical pixels.

        Anchor for `[MOVE:to;x;y]` and `foot_position_*`: the sprite is
        rendered with `SPRITE_OFFSET_X` plus a panel reserve, so the
        window's geometric centre/bottom sits far from where Doro's
        sprite actually appears. Computing the offset off the same
        `calculate_sprite_center` the painter uses keeps movement /
        click / overlay anchored to the visible sprite, not the
        invisible window frame.
        """
        sprite_center, _ = self._rendering_engine.calculate_sprite_center(
            self.size(),
            self._sprite_anchor_top,
            self._panel_height_hint,
            reserve_above=self._bubble_above,
        )
        half_h = self._view_model.sprite_size.height() / 2.0
        return QtCore.QPoint(
            int(round(sprite_center.x())),
            int(round(sprite_center.y() + half_h)) - 1,
        )

    def logical_point_for_physical(self, x: int, y: int) -> QtCore.QPoint:
        """Convert an OS physical pixel (a11y/mouse space) to a Qt logical point.

        Used by `[move:to]` so a coordinate the LLM read off the element tree
        lands at the right spot even when the display is scaled (DPR != 1).
        """
        from ..core.automation.coordinates import compute_logical_point_from_physical

        screen = self.screen()
        if screen is None:
            return QtCore.QPoint(int(x), int(y))
        geom = screen.geometry()
        lx, ly = compute_logical_point_from_physical(
            (int(x), int(y)),
            screen_origin_logical=(geom.x(), geom.y()),
            device_pixel_ratio=screen.devicePixelRatio(),
        )
        return QtCore.QPoint(lx, ly)

    def get_bubble_offset(self) -> QtCore.QPointF:
        """Get the current bubble offset (public API for movement)."""
        if self._bubble_controller:
            return self._bubble_controller.offset
        return QtCore.QPointF(BUBBLE_DEFAULT_OFFSET_X, BUBBLE_DEFAULT_OFFSET_Y)

    def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False):
        """Apply bubble offset via BubbleController (public API)."""
        if self._bubble_controller:
            self._bubble_controller.apply_offset(offset, persist=persist)

    def reset_tick_timer(self, value: float):
        """Reset the tick timer used for movement animation (public API)."""
        self._last_tick_time = value

    # ═══════════════════════════════════════════════════════════
    # Event Callbacks from StateService and TransitionPlayer
    # ═══════════════════════════════════════════════════════════

    def on_transition_movie_loaded(self, movie: QtGui.QMovie, sprite_size: QtCore.QSize):
        """Handle transition movie loaded signal from TransitionPlayer."""
        if self._sprite_controller:
            self._sprite_controller.set_movie_directly(movie, sprite_size)

    def set_busy_cursor(self, enabled: bool):
        if enabled and not self._chat_cursor_overridden:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
            self._chat_cursor_overridden = True
        elif not enabled and self._chat_cursor_overridden:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._chat_cursor_overridden = False

    def toggle_bubble(self, checked: bool):
        if not self._current_state_key:
            return
        self.bubble_toggle_requested.emit(self._current_state_key, checked)

    def _set_bubble_text(
        self,
        text: str,
        override_visibility: bool = True,
        *,
        auto_hide: bool = True,
        hide_delay_ms: int | None = None,
    ):
        self._bubble_controller.set_text(
            text,
            override_visibility=override_visibility,
            auto_hide=auto_hide,
            hide_delay_ms=hide_delay_ms,
        )

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.set_busy_cursor(False)

        # Clean up resources
        try:
            # Clear all GIF resources via SpriteController
            if self._sprite_controller:
                # Dispose ALL renderers (release any renderer-held resources)
                self._sprite_controller.dispose_all()
                self._sprite_controller.gif_player.clear()

            if self._timer:
                try:
                    self._timer.stop()
                except Exception:
                    pass

            # Save configuration on close
            if self._config_manager:
                self._config_manager.save()
        except Exception:
            pass

        super().closeEvent(event)
