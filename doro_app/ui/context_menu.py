"""Context menu builder for the desktop companion window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from .chat_settings import ChatSettingsDialog

if TYPE_CHECKING:
    from ..window import DoroWindow


class ContextMenuManager:
    """Build and display the right-click menu for :class:`DoroWindow`."""

    def __init__(self, window: DoroWindow, chat_settings: ChatSettingsDialog):
        self._window = window
        self._chat_settings = chat_settings

    def exec(self, event: QtGui.QContextMenuEvent) -> None:
        window = self._window
        window.mark_user_activity()
        menu = QtWidgets.QMenu(window)

        self._populate_states_menu(menu)
        self._populate_actions_menu(menu)
        self._populate_visuals_menu(menu)
        self._populate_chat_menu(menu)

        menu.addSeparator()
        quit_action = QtGui.QAction("Exit doro", window)
        quit_action.triggered.connect(QtWidgets.QApplication.instance().quit)
        menu.addAction(quit_action)

        restart_action = QtGui.QAction("Restart doro", window)
        restart_action.triggered.connect(window.restart_app)
        menu.addAction(restart_action)

        menu.exec(event.globalPos())

    # ------------------------------------------------------------------ Builders

    def _populate_states_menu(self, menu: QtWidgets.QMenu) -> None:
        window = self._window
        state_manager = window.state_manager
        states_menu = menu.addMenu("States")
        for key in window.visible_state_keys():
            state = window.state_definitions.get(key)
            if state is None:
                continue
            label = state.label or key
            action = states_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == window.current_state_key)
            action.triggered.connect(lambda checked, s=key: window.set_state(s))

        edit_states_action = states_menu.addAction("Edit states")
        edit_states_action.triggered.connect(state_manager.show_state_gif_manager)

        remove_action = states_menu.addAction("Remove current state")
        remove_action.setEnabled(
            bool(window.current_state_key)
            and window.current_state_key not in window.protected_state_keys
        )
        remove_action.triggered.connect(state_manager.remove_current_state)

    def _populate_actions_menu(self, menu: QtWidgets.QMenu) -> None:
        window = self._window
        state_manager = window.state_manager
        actions_menu = menu.addMenu("Actions")
        edit_actions_action = actions_menu.addAction("Edit actions")
        edit_actions_action.triggered.connect(state_manager.show_move_gif_manager)

    def _populate_visuals_menu(self, menu: QtWidgets.QMenu) -> None:
        window = self._window
        visuals_menu = menu.addMenu("State visuals")
        bubble_action = visuals_menu.addAction("Show message panel")
        bubble_action.setCheckable(True)
        bubble_action.setChecked(window.state_settings and window.state_settings.bubble_visible)
        bubble_action.triggered.connect(window.toggle_bubble)

        gif_action = visuals_menu.addAction("Load GIF")
        gif_action.triggered.connect(window.load_state_gif)

        clear_gif_action = visuals_menu.addAction("Reset GIF to default")
        clear_gif_action.setEnabled(window.default_idle_gif_exists)
        clear_gif_action.triggered.connect(window.clear_state_gif)

        name_tag_action = visuals_menu.addAction("Rename pet")
        name_tag_action.triggered.connect(window.rename_pet)

        menu.addSeparator()

        top_action = QtGui.QAction("Stay on top", window)
        top_action.setCheckable(True)
        is_top = bool(window.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)
        top_action.setChecked(is_top)

        def toggle_top() -> None:
            flags = window.windowFlags()
            if bool(flags & QtCore.Qt.WindowType.WindowStaysOnTopHint):
                flags &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
            else:
                flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
            window.setWindowFlags(flags)
            window.show()

        top_action.triggered.connect(toggle_top)
        menu.addAction(top_action)

    def _populate_chat_menu(self, menu: QtWidgets.QMenu) -> None:
        window = self._window
        chat_menu = menu.addMenu("Chat")
        ask_action = chat_menu.addAction("Ask Doro")
        ask_action.setEnabled(not window.chat_orchestrator.is_inflight)
        ask_action.triggered.connect(window.prompt_chat)

        edit_prompt_action = chat_menu.addAction("Edit prompt")
        edit_prompt_action.triggered.connect(window.edit_chat_prompt)

        clear_history_action = chat_menu.addAction("Clear conversation history")
        clear_history_action.setEnabled(window.chat_controller.has_history)
        clear_history_action.triggered.connect(window.clear_chat_history)

        configure_menu = chat_menu.addMenu("Configure")

        server_action = configure_menu.addAction("Set server URL")
        server_action.triggered.connect(self._chat_settings.configure_server)

        model_action = configure_menu.addAction("Set model name")
        model_action.triggered.connect(self._chat_settings.configure_model)

        endpoint_action = configure_menu.addAction("Set endpoint path")
        endpoint_action.triggered.connect(self._chat_settings.configure_endpoint)

        temperature_action = configure_menu.addAction("Set temperature")
        temperature_action.triggered.connect(self._chat_settings.configure_temperature)

        timeout_action = configure_menu.addAction("Set timeout (seconds)")
        timeout_action.triggered.connect(self._chat_settings.configure_timeout)
