"""Tests for ActionRepository — actions.json persistence + click builtin."""

from __future__ import annotations

import json

import pytest

from doro_app.core.action.repository import (
    CLICK_ACTION_KEY,
    DRAG_ACTION_KEY,
    ActionEntry,
    ActionRepository,
)


@pytest.fixture
def actions_path(tmp_path):
    return tmp_path / "actions.json"


def test_load_creates_click_builtin_when_file_missing(actions_path):
    repo = ActionRepository(actions_path)
    repo.load()

    click = repo.get(CLICK_ACTION_KEY)
    assert click is not None
    assert click.key == CLICK_ACTION_KEY
    assert click.is_builtin is True
    assert click.gif_id is None
    assert click.display_name == "Click"


def test_load_preserves_user_gif_id_from_existing_file(actions_path):
    actions_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "key": CLICK_ACTION_KEY,
                        "display_name": "Click",
                        "gif_id": "click/my_winding.gif",
                        "is_builtin": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repo = ActionRepository(actions_path)
    repo.load()

    click = repo.get(CLICK_ACTION_KEY)
    assert click is not None
    assert click.gif_id == "click/my_winding.gif"
    assert click.is_builtin is True


def test_load_reaffirms_builtin_flag_even_if_stored_as_false(actions_path):
    actions_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "key": CLICK_ACTION_KEY,
                        "display_name": "Click",
                        "gif_id": None,
                        "is_builtin": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repo = ActionRepository(actions_path)
    repo.load()

    # The builtin flag MUST be authoritative — we never want a user to
    # accidentally turn click into a non-builtin and then remove it.
    assert repo.get(CLICK_ACTION_KEY).is_builtin is True


def test_load_tolerates_corrupted_json(actions_path):
    actions_path.write_text("{not valid json", encoding="utf-8")

    repo = ActionRepository(actions_path)
    repo.load()
    # Corrupted file: warning logged, click builtin still gets created.
    assert repo.get(CLICK_ACTION_KEY) is not None


def test_update_gif_id_persists_and_returns_true(actions_path):
    repo = ActionRepository(actions_path)
    repo.load()

    assert repo.update_gif_id(CLICK_ACTION_KEY, "user/upload.gif") is True

    # Reload from disk to confirm persistence.
    fresh = ActionRepository(actions_path)
    fresh.load()
    assert fresh.get(CLICK_ACTION_KEY).gif_id == "user/upload.gif"


def test_update_gif_id_to_none_clears_binding(actions_path):
    repo = ActionRepository(actions_path)
    repo.load()
    repo.update_gif_id(CLICK_ACTION_KEY, "something.gif")
    repo.update_gif_id(CLICK_ACTION_KEY, None)

    fresh = ActionRepository(actions_path)
    fresh.load()
    assert fresh.get(CLICK_ACTION_KEY).gif_id is None


def test_update_gif_id_returns_false_for_unknown_key(actions_path):
    repo = ActionRepository(actions_path)
    repo.load()
    assert repo.update_gif_id("nonexistent_action", "x.gif") is False


def test_actionentry_round_trip_through_dict():
    entry = ActionEntry(key="click", display_name="Click", gif_id="x.gif", is_builtin=True)
    restored = ActionEntry.from_dict(entry.to_dict())
    assert restored == entry


def test_actionentry_from_dict_fills_defaults():
    # Older actions.json may only carry `key` — display_name and flags
    # should be reconstructed without crashing.
    entry = ActionEntry.from_dict({"key": "click"})
    assert entry.key == "click"
    assert entry.display_name == "Click"
    assert entry.gif_id is None
    assert entry.is_builtin is False
    # Legacy files predate `kind`; they default to the click action.
    assert entry.kind == "click"


def test_load_creates_dragged_builtin(actions_path):
    repo = ActionRepository(actions_path)
    repo.load()

    dragged = repo.get(DRAG_ACTION_KEY)
    assert dragged is not None
    assert dragged.is_builtin is True
    assert dragged.kind == "dragged"
    assert dragged.gif_id is None
    assert dragged.display_name == "拖曳"


def test_load_preserves_dragged_user_gif_but_reaffirms_kind(actions_path):
    actions_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "key": DRAG_ACTION_KEY,
                        "display_name": "拖曳",
                        "gif_id": "dragged/mine.webp",
                        "is_builtin": False,  # must be re-asserted True
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repo = ActionRepository(actions_path)
    repo.load()

    dragged = repo.get(DRAG_ACTION_KEY)
    assert dragged.gif_id == "dragged/mine.webp"  # user binding survives
    assert dragged.is_builtin is True             # builtin flag authoritative
    assert dragged.kind == "dragged"
