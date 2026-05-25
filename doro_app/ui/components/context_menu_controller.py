"""Controller that builds and shows the right-click context menu."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from ...utils.paths import LIVE2D_MODEL_PATH
from ..theme.themed_menu import (
    MenuCallbacks,
    MenuSnapshot,
    build_context_menu_content,
    create_doro_menu,
)

try:
    from ..rendering.live2d_sprite_renderer import _LIVE2D_AVAILABLE
except ImportError:
    _LIVE2D_AVAILABLE = False

if TYPE_CHECKING:
    from ..components.bubble_controller import BubbleController
    from ..helpers import ChatUIHelper
    from ..window import DoroWindow
    from ...core.core_manager import CoreManager
    from ...core.state import StateService
    from ..controllers import DialogManager, StateController


class ContextMenuController:
    """Assembles MenuSnapshot + MenuCallbacks and shows the themed context menu."""

    def __init__(
        self,
        *,
        window: DoroWindow,
        state_service: StateService,
        state_controller: StateController,
        dialog_manager: DialogManager,
        bubble_controller: BubbleController,
        core_manager: CoreManager,
        chat_ui: ChatUIHelper,
        default_idle_gif: Path,
        reload_sprite: Callable[[str], None] | None = None,
    ) -> None:
        self._window = window
        self._state_service = state_service
        self._state_controller = state_controller
        self._dialog_manager = dialog_manager
        self._bubble_controller = bubble_controller
        self._core_manager = core_manager
        self._chat_ui = chat_ui
        self._default_idle_gif = default_idle_gif
        self._reload_sprite = reload_sprite

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def show(self, global_pos: QtCore.QPoint) -> None:
        """Build and display the context menu at *global_pos*."""
        menu = create_doro_menu(
            parent=self._window,
            avatar_position="top-center",
            avatar_pixmap=self._window.sprite_renderer.current_pixmap(),
        )
        snapshot = self._build_snapshot()
        cbs = self._build_callbacks()
        build_context_menu_content(menu, self._window, snapshot, cbs)

        if hasattr(menu, "exec"):
            menu.exec(global_pos)
        else:
            menu.exec_(global_pos)

    # ──────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────

    def _build_snapshot(self) -> MenuSnapshot:
        current_state = self._state_service.get_current_state()
        states: list[tuple[str, str]] = []
        for key in self._state_controller.visible_state_keys():
            state = self._state_service.get_state(key)
            if state:
                states.append((key, state.label or key))
        return MenuSnapshot(
            visible_states=states,
            current_state_key=self._window.current_state_key,
            is_topmost=bool(
                self._window.windowFlags()
                & QtCore.Qt.WindowType.WindowStaysOnTopHint
            ),
            bubble_visible=bool(
                current_state and current_state.visual.bubble_visible
            ),
            has_default_idle_gif=self._default_idle_gif.is_file(),
            is_chat_inflight=self._core_manager.is_chat_inflight,
            has_chat_history=self._core_manager.has_chat_history,
            using_live2d=bool(
                current_state and current_state.live2d_model_path
            ),
            live2d_available=_LIVE2D_AVAILABLE,
        )

    def _build_callbacks(self) -> MenuCallbacks:
        current_key = self._window.current_state_key
        return MenuCallbacks(
            set_state=self._state_controller.set_state,
            show_state_manager=self._dialog_manager.show_state_manager,
            show_move_state_manager=self._dialog_manager.show_move_state_manager,
            toggle_bubble=self._window.toggle_bubble,
            clear_state_gif=lambda: self._state_controller.clear_state_gif(
                current_key
            ),
            toggle_live2d=lambda checked: self._toggle_live2d(current_key, checked),
            show_rename_dialog=lambda: (
                self._dialog_manager.show_rename_dialog(current_key)
                and self._window.update()
            )
            if current_key
            else None,
            prompt_chat=self._chat_ui.prompt_chat,
            edit_chat_prompt=self._chat_ui.edit_chat_prompt,
            clear_chat_history=self._chat_ui.clear_chat_history,
            open_settings_dialog=self._chat_ui.open_settings_dialog,
            quit_app=QtWidgets.QApplication.instance().quit,
        )

    def _toggle_live2d(self, state_key: str | None, checked: bool) -> None:
        """Toggle Live2D mode globally (applies to all states)."""
        if not state_key:
            return
        if checked:
            self._state_controller.set_live2d_model_all(LIVE2D_MODEL_PATH)
        else:
            self._state_controller.clear_live2d_model_all()
        # Reload sprite for the current state
        if self._reload_sprite:
            self._reload_sprite(state_key)
