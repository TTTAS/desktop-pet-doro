"""State controller - coordinates state changes with UI updates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from ...core.state import StateChangeEvent, StateService
from ...utils.config_manager import ConfigManager
from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ..viewmodels.doro_viewmodel import DoroViewModel

logger = get_logger(__name__)


class StateController(QtCore.QObject):
    """
    Coordinates state changes between StateService and ViewModel.

    Responsibilities:
    - Listen to StateService state change events
    - Apply visual state configuration to ViewModel
    - Trigger UI repaints when state changes
    - Provide state query helpers for UI
    """

    # Signals
    repaint_requested = QtCore.Signal()
    state_changed = QtCore.Signal(str)  # new_state_key
    state_list_updated = QtCore.Signal(str)  # state_list_text

    def __init__(
        self,
        state_service: StateService,
        view_model: DoroViewModel,
        config: QtCore.QSettings | None = None,
        config_manager: ConfigManager | None = None,
    ):
        """
        Initialize StateController.

        Args:
            state_service: State management service
            view_model: Presentation state ViewModel
            config: (Legacy) QSettings for persistence
            config_manager: ConfigManager for type-safe config access
        """
        super().__init__()
        self._state_service = state_service
        self._view_model = view_model
        self._config = config  # Legacy - kept for backward compatibility
        self._config_manager = config_manager
        self._current_state_key = ""

        # Connect to StateService events
        self._state_service.on_state_changed = self._on_state_changed
        self._state_service.on_states_modified = self._on_states_modified

    @property
    def current_state_key(self) -> str:
        """Get current state key."""
        return self._current_state_key

    def _on_state_changed(self, event: StateChangeEvent) -> None:
        """
        Handle state change events from StateService.

        Applies visual configuration to ViewModel and triggers repaint.
        """
        state = event.new_state
        self._current_state_key = event.new_key

        # Update state list text
        state_list_text = self._state_service.write_state_list()
        self.state_list_updated.emit(state_list_text)

        # Apply visual config to ViewModel
        visual = state.visual
        self._view_model.set_bob_amplitude(visual.bob_amplitude)
        self._view_model.set_scale_amplitude(visual.scale_amplitude)
        self._view_model.set_fill_colors(
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._view_model.set_cheek_alpha(visual.cheeks_alpha)
        self._view_model.set_blush_color(QtGui.QColor(visual.blush_color))
        self._view_model.set_eye_color(QtGui.QColor(visual.eye_color))
        self._view_model.set_bubble_visible(visual.bubble_visible)
        self._view_model.set_bubble_alpha(visual.bubble_alpha)
        self._view_model.set_name_tag(state.name_tag)

        # Persist to config
        if self._config_manager:
            # Use ConfigManager for type-safe config access
            self._config_manager.update_app(current_state=event.new_key)
            self._config_manager.save()
        elif self._config:
            # Fallback to legacy QSettings
            self._config.setValue("current_state", event.new_key)

        # Notify
        self.state_changed.emit(event.new_key)
        self.repaint_requested.emit()

    def _on_states_modified(self) -> None:
        """Handle state list modifications (add/remove states)."""
        state_list_text = self._state_service.write_state_list()
        self.state_list_updated.emit(state_list_text)

    def apply_state_settings(self, state_key: str | None = None) -> None:
        """
        Apply state visual settings to ViewModel.

        Args:
            state_key: State key to apply (uses current if None)
        """
        key = state_key or self._current_state_key
        if not key:
            return

        state = self._state_service.get_state(key)
        if not state:
            return

        # Apply visual config to ViewModel
        visual = state.visual
        self._view_model.set_bob_amplitude(visual.bob_amplitude)
        self._view_model.set_scale_amplitude(visual.scale_amplitude)
        self._view_model.set_fill_colors(
            QtGui.QColor(visual.gradient_top),
            QtGui.QColor(visual.gradient_mid),
            QtGui.QColor(visual.gradient_bottom),
        )
        self._view_model.set_cheek_alpha(visual.cheeks_alpha)
        self._view_model.set_blush_color(QtGui.QColor(visual.blush_color))
        self._view_model.set_eye_color(QtGui.QColor(visual.eye_color))
        self._view_model.set_bubble_visible(visual.bubble_visible)
        self._view_model.set_bubble_alpha(visual.bubble_alpha)
        self._view_model.set_name_tag(state.name_tag)

        self.repaint_requested.emit()

    # ─────────────────────────────────────────────────────────
    # Convenience methods for UI (delegates to StateService)
    # ─────────────────────────────────────────────────────────

    def set_state(self, key: str) -> bool:
        """Set current state (delegates to StateService)."""
        return self._state_service.set_state(key)

    def set_state_gif(self, key: str, source_path: Path) -> bool:
        """Set GIF for a state (delegates to StateService)."""
        return self._state_service.set_gif(key, source_path)

    def clear_state_gif(self, state_key: str | None = None) -> bool:
        """
        Clear GIF for a state.

        Args:
            state_key: State key (uses current if None)

        Returns:
            True if GIF was cleared
        """
        key = state_key or self._current_state_key
        if not key:
            return False

        state = self._state_service.get_state(key)
        if not state or not state.gif_id:
            return False

        self._state_service.delete_gif(state.gif_id)
        self._state_service.update_state(key, gif_id=None)
        return True

    def is_movement_only_state(self, key: str) -> bool:
        """Check if state is movement-only."""
        return self._state_service.is_movement_only_state(key)

    def visible_state_keys(self) -> list[str]:
        """Get list of visible state keys."""
        return self._state_service.visible_state_keys()

    def get_state_list_text(self) -> str:
        """Get formatted state list text."""
        return self._state_service.write_state_list()
