"""Controller that builds and shows the right-click context menu."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from ..theme.themed_menu import (
    MenuCallbacks,
    MenuSnapshot,
    build_context_menu_content,
    create_doro_menu,
)

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
    ) -> None:
        self._window = window
        self._state_service = state_service
        self._state_controller = state_controller
        self._dialog_manager = dialog_manager
        self._bubble_controller = bubble_controller
        self._core_manager = core_manager
        self._chat_ui = chat_ui
        self._default_idle_gif = default_idle_gif

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
            is_topmost=bool(self._window.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint),
            bubble_visible=bool(current_state and current_state.visual.bubble_visible),
            has_default_idle_gif=self._default_idle_gif.is_file(),
            is_chat_inflight=self._core_manager.is_chat_inflight,
            has_chat_history=self._core_manager.has_chat_history,
            a11y_enabled=bool(self._core_manager.config_manager.automation.a11y_enabled),
            mouse_enabled=bool(self._core_manager.config_manager.automation.mouse_enabled),
        )

    def _build_callbacks(self) -> MenuCallbacks:
        current_key = self._window.current_state_key
        return MenuCallbacks(
            set_state=self._state_controller.set_state,
            show_state_manager=self._dialog_manager.show_state_manager,
            show_move_state_manager=self._dialog_manager.show_move_state_manager,
            toggle_bubble=self._window.toggle_bubble,
            clear_state_gif=lambda: self._state_controller.clear_state_gif(current_key),
            show_rename_dialog=lambda: (
                (self._dialog_manager.show_rename_dialog(current_key) and self._window.update())
                if current_key
                else None
            ),
            prompt_chat=self._chat_ui.prompt_chat,
            edit_chat_prompt=self._chat_ui.edit_chat_prompt,
            clear_chat_history=self._chat_ui.clear_chat_history,
            open_settings_dialog=self._chat_ui.open_settings_dialog,
            toggle_a11y=self._toggle_a11y,
            preview_a11y=self._preview_a11y,
            toggle_mouse_enabled=self._toggle_mouse_enabled,
            simulate_response=self._simulate_response,
            inspect_position=self._inspect_position,
            quit_app=QtWidgets.QApplication.instance().quit,
        )

    def _toggle_a11y(self, checked: bool) -> None:
        """Flip accessibility tree reading on/off and persist it.

        The A11yService reads this flag live on every read, so no restart is
        needed.
        """
        cm = self._core_manager.config_manager
        cm.update_automation(a11y_enabled=bool(checked))
        cm.save()
        if checked and self._core_manager.a11y_service is not None:
            self._core_manager.a11y_service.clear_session_blacklist()

    def _toggle_mouse_enabled(self, checked: bool) -> None:
        """Flip mouse-click automation on/off and persist.

        AutomationManager self-gates on this flag at execute_click time,
        so no restart is needed — once pynput is available, toggling
        lights it up immediately.
        """
        cm = self._core_manager.config_manager
        cm.update_automation(mouse_enabled=bool(checked))
        cm.save()

    def _preview_a11y(self) -> None:
        """Run the diagnostic read and show the result in a popup.

        No countdown is needed: the foreground tracker already points at the
        last external window the user was using, so the preview reads that
        directly instead of Doro's own (just-clicked) window.
        """
        service = self._core_manager.a11y_service
        if service is None:
            QtWidgets.QMessageBox.information(
                self._window, "Doro", "a11y 服務未建立（初始化可能失敗）。"
            )
            return
        self._show_a11y_result(service)

    def _show_a11y_result(self, service) -> None:
        ok, message = service.diagnose_foreground_tree()
        title = "Doro 現在看到" if ok else "目前讀不到內容"
        QtWidgets.QMessageBox.information(self._window, title, message)

    def _inspect_position(self) -> None:
        """Show window/sprite-foot/last-target coordinates for debugging
        `[move:to;x;y]` landing precision. Result is also copied to clipboard
        so the user can paste it back to verify foot-vs-target drift."""
        win = self._window
        mm = self._core_manager.movement_manager
        top_left = win.current_position()
        foot_offset = win.sprite_foot_offset_logical()
        foot_logical = QtCore.QPoint(
            top_left.x() + foot_offset.x(),
            top_left.y() + foot_offset.y(),
        )
        screen = win.screen()
        if screen is not None:
            from ...core.automation.coordinates import compute_physical_pixel_at

            geom = screen.geometry()
            foot_phys = compute_physical_pixel_at(
                (foot_logical.x(), foot_logical.y()),
                screen_origin_logical=(geom.x(), geom.y()),
                device_pixel_ratio=screen.devicePixelRatio(),
            )
        else:
            foot_phys = (foot_logical.x(), foot_logical.y())

        last_target = mm.last_target_physical
        if last_target is not None:
            dx = foot_phys[0] - last_target[0]
            dy = foot_phys[1] - last_target[1]
            delta_str = f"({dx:+d}, {dy:+d})"
            target_str = f"{last_target[0]}, {last_target[1]}"
        else:
            delta_str = "—"
            target_str = "—"

        msg = (
            f"window top-left (logical): {top_left.x()}, {top_left.y()}\n"
            f"sprite foot offset (logical): {foot_offset.x()}, {foot_offset.y()}\n"
            f"sprite foot (logical): {foot_logical.x()}, {foot_logical.y()}\n"
            f"sprite foot (physical): {foot_phys[0]}, {foot_phys[1]}\n"
            f"last [move:to] target (physical): {target_str}\n"
            f"foot − target: {delta_str}"
        )
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(msg)
        QtWidgets.QMessageBox.information(win, "Doro 位置（已複製到剪貼簿）", msg)

    def _simulate_response(self) -> None:
        """Prompt for a fake assistant reply and run it through the exact same
        handling a real server reply gets (movement/state/mouse parsing), so the
        user can test Doro without hitting the server."""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self._window,
            "假傳伺服器回應",
            "輸入要模擬的回應（例：(walking) 幫人點～ [MOVE:to;x=180;y=100] [mouse:click]）：",
        )
        if not ok or not text.strip():
            return
        dialogue = self._core_manager.chat_orchestrator.simulate_response(text.strip())
        if not dialogue:
            QtWidgets.QMessageBox.information(
                self._window, "Doro", "（這段回應只有動作／狀態指令，沒有對話）"
            )
