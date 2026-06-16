"""Tests for EditMoveStateDialog (focus on Phase 1c Action mode wiring)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from doro_app.core.action.repository import CLICK_ACTION_KEY


@pytest.fixture
def fake_state_service():
    """Minimal StateService stand-in covering the slice the dialog uses."""
    svc = Mock()
    svc.visible_state_keys.return_value = ["idle", "happy"]
    svc.get_state.return_value = None
    svc.get_gif_path_by_id.return_value = None
    svc.list_transition_gif_paths.return_value = []
    return svc


@pytest.fixture
def fake_action_service(tmp_path):
    """Minimal ActionService stand-in."""
    svc = Mock()
    svc.resolve_action_gif_path.return_value = None  # no GIF yet bound
    svc.bind_click_gif.return_value = True
    return svc


def _import_dialog():
    """Local import so tests can run without Qt initialized at collection."""
    from doro_app.ui.dialogs.move_state.edit_dialog import EditMoveStateDialog
    return EditMoveStateDialog


def test_action_option_appears_when_action_service_passed(qtbot, fake_state_service, fake_action_service):
    EditMoveStateDialog = _import_dialog()
    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
    )
    qtbot.addWidget(dialog)
    items = [dialog.type_combo.itemText(i) for i in range(dialog.type_combo.count())]
    assert "Action" in items


def test_action_option_absent_without_action_service(qtbot, fake_state_service):
    EditMoveStateDialog = _import_dialog()
    dialog = EditMoveStateDialog(fake_state_service, None)
    qtbot.addWidget(dialog)
    items = [dialog.type_combo.itemText(i) for i in range(dialog.type_combo.count())]
    assert "Action" not in items
    # Legacy two-option menu must stay intact.
    assert items == ["Movement", "Transition"]


def test_selecting_action_locks_key_to_click(qtbot, fake_state_service, fake_action_service):
    EditMoveStateDialog = _import_dialog()
    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
    )
    qtbot.addWidget(dialog)

    dialog.type_combo.setCurrentText("Action")

    assert dialog.action_type == "action"
    assert dialog.key_edit.text() == CLICK_ACTION_KEY
    assert dialog.key_edit.isEnabled() is False
    # Movement / transition fields hidden in action mode.
    assert dialog.state_combo.isHidden() is True
    assert dialog.from_state_combo.isHidden() is True


def test_action_edit_mode_loads_existing_binding_path(
    qtbot, fake_state_service, fake_action_service, tmp_path,
):
    EditMoveStateDialog = _import_dialog()
    existing_gif = tmp_path / "currently_bound.gif"
    existing_gif.write_bytes(b"gif")
    fake_action_service.resolve_action_gif_path.return_value = existing_gif

    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
        edit_action_key=CLICK_ACTION_KEY,
    )
    qtbot.addWidget(dialog)

    # The dialog should have asked the ActionService for the current path.
    fake_action_service.resolve_action_gif_path.assert_called_with(CLICK_ACTION_KEY)
    # And surfaced its filename in the status label.
    assert "currently_bound.gif" in dialog.gif_status_label.text()
    # Action mode is active without the user touching the combo.
    assert dialog.action_type == "action"
    assert dialog.key_edit.text() == CLICK_ACTION_KEY


def test_save_action_calls_bind_click_gif(
    qtbot, fake_state_service, fake_action_service, tmp_path,
):
    EditMoveStateDialog = _import_dialog()
    selected = tmp_path / "user_choice.gif"
    selected.write_bytes(b"gif")

    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
        edit_action_key=CLICK_ACTION_KEY,
    )
    qtbot.addWidget(dialog)

    dialog.selected_gif_path = selected
    dialog._on_accept()

    fake_action_service.bind_click_gif.assert_called_once_with(selected)


def test_save_action_with_no_selection_does_not_call_service(
    qtbot, fake_state_service, fake_action_service,
):
    """Closing the action dialog without picking a GIF is a no-op."""
    EditMoveStateDialog = _import_dialog()
    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
        edit_action_key=CLICK_ACTION_KEY,
    )
    qtbot.addWidget(dialog)

    dialog._on_accept()
    fake_action_service.bind_click_gif.assert_not_called()


def test_movement_mode_still_works_alongside_action_service(
    qtbot, fake_state_service, fake_action_service,
):
    """Adding an Action option must not break the legacy Movement flow."""
    EditMoveStateDialog = _import_dialog()
    dialog = EditMoveStateDialog(
        fake_state_service, None,
        action_service=fake_action_service,
    )
    qtbot.addWidget(dialog)

    dialog.type_combo.setCurrentText("Movement")
    assert dialog.action_type == "movement"
    assert dialog.state_combo.isHidden() is False
    # Key is editable again after leaving Action mode.
    assert dialog.key_edit.isEnabled() is True
