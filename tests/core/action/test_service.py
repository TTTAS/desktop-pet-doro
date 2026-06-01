"""Tests for ActionService bootstrap + GIF fallback + binding."""

from __future__ import annotations

from pathlib import Path

import pytest

from doro_app.core.action.fakes import FakeActionRepository
from doro_app.core.action.repository import ActionEntry, CLICK_ACTION_KEY
from doro_app.core.action.service import (
    CLICK_ACTION_STATE_KEY,
    CLICK_ACTION_STATE_LABEL,
    ActionService,
)


class FakeGifRepository:
    """Mimics the slice of GifRepository the service consumes."""

    def __init__(self, storage_dir: Path, files: dict[str, Path] | None = None):
        self.storage_dir = storage_dir
        self._files: dict[str, Path] = files or {}
        self._random_gif_for_state: dict[str, Path | None] = {}

    def get_path(self, gif_id: str) -> Path | None:
        path = self._files.get(gif_id)
        if path and path.is_file():
            return path
        return None

    def pick_random_gif(self, state_key: str) -> Path | None:
        return self._random_gif_for_state.get(state_key)


class RecordingStateService:
    """Captures ensure_action_state / update_state / store_gif calls."""

    def __init__(self):
        self.ensure_calls: list[tuple[str, str, str | None]] = []
        self.update_calls: list[tuple[str, dict]] = []
        self.store_returns: str | None = "stored_gif_id"

    def ensure_action_state(self, *, key, label, gif_id=None):
        self.ensure_calls.append((key, label, gif_id))

    def update_state(self, key, **changes):
        self.update_calls.append((key, dict(changes)))
        return True

    def store_gif(self, source_path, state_key):
        return self.store_returns


# ─── Bootstrap behaviour ──────────────────────────────────────────


def test_bootstrap_registers_click_state_with_user_bound_gif(tmp_path):
    """When user has bound a GIF, it propagates to the State."""
    storage = tmp_path / "state"
    storage.mkdir()
    user_gif = storage / "click" / "user.gif"
    user_gif.parent.mkdir(parents=True)
    user_gif.write_bytes(b"gif data")

    repo = FakeActionRepository([
        ActionEntry(key=CLICK_ACTION_KEY, display_name="Click",
                    gif_id="click/user.gif", is_builtin=True)
    ])
    gif_repo = FakeGifRepository(storage, files={"click/user.gif": user_gif})
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    service.bootstrap()

    # Both click_action and click_failed get the same gif_id by default —
    # the user can bind click_failed independently later via the UI but
    # at bootstrap they share the effective fallback chain.
    from doro_app.core.action.service import (
        CLICK_FAILED_STATE_KEY,
        CLICK_FAILED_STATE_LABEL,
    )
    assert state_service.ensure_calls == [
        (CLICK_ACTION_STATE_KEY, CLICK_ACTION_STATE_LABEL, "click/user.gif"),
        (CLICK_FAILED_STATE_KEY, CLICK_FAILED_STATE_LABEL, "click/user.gif"),
    ]


def test_bootstrap_falls_back_to_random_stand_when_no_user_binding(tmp_path):
    """Without user binding, picks a random stand/ GIF for the state."""
    storage = tmp_path / "state"
    storage.mkdir()
    stand_random = storage / "stand" / "stand_2.gif"
    stand_random.parent.mkdir(parents=True)
    stand_random.write_bytes(b"gif data")

    repo = FakeActionRepository()  # no user binding
    gif_repo = FakeGifRepository(storage)
    gif_repo._random_gif_for_state["stand"] = stand_random
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    service.bootstrap()

    # The fallback gif_id should be a forward-slash relative path under
    # storage_dir so GifRepository.get_path can resolve it later. Both
    # click_action and click_failed are registered with the same
    # bootstrap-time fallback.
    assert len(state_service.ensure_calls) == 2
    keys = [c[0] for c in state_service.ensure_calls]
    assert keys[0] == CLICK_ACTION_STATE_KEY
    for _, _, gif_id in state_service.ensure_calls:
        assert gif_id == "stand/stand_2.gif"


def test_bootstrap_falls_back_to_single_stand_gif(tmp_path):
    """When stand/ subfolder is empty, fall back to res/state/stand.gif."""
    storage = tmp_path / "state"
    storage.mkdir()
    stand_single = storage / "stand.gif"
    stand_single.write_bytes(b"gif data")

    repo = FakeActionRepository()
    gif_repo = FakeGifRepository(storage, files={"stand.gif": stand_single})
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    service.bootstrap()

    _, _, gif_id = state_service.ensure_calls[0]
    assert gif_id == "stand.gif"


def test_bootstrap_falls_back_to_idle_when_no_stand(tmp_path):
    """Final fallback: idle.gif (always provisioned by app bootstrap)."""
    storage = tmp_path / "state"
    storage.mkdir()
    idle = storage / "idle.gif"
    idle.write_bytes(b"gif data")

    repo = FakeActionRepository()
    gif_repo = FakeGifRepository(storage, files={"idle.gif": idle})
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    service.bootstrap()

    _, _, gif_id = state_service.ensure_calls[0]
    assert gif_id == "idle.gif"


def test_bootstrap_with_no_assets_at_all_passes_none(tmp_path):
    """If even idle.gif is missing, ensure_action_state still runs with None.

    The State machinery handles None gracefully (renderer falls back to
    whatever transition / movement assets are available), so the click
    feature is never broken by missing assets.
    """
    storage = tmp_path / "state"
    storage.mkdir()

    repo = FakeActionRepository()
    gif_repo = FakeGifRepository(storage)
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    service.bootstrap()

    _, _, gif_id = state_service.ensure_calls[0]
    assert gif_id is None


def test_bootstrap_uses_default_idle_gif_when_repo_lookup_misses(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()
    out_of_repo_idle = tmp_path / "external_idle.gif"
    out_of_repo_idle.write_bytes(b"gif")

    repo = FakeActionRepository()
    gif_repo = FakeGifRepository(storage)
    state_service = RecordingStateService()

    service = ActionService(
        repo, state_service, gif_repo, default_idle_gif=out_of_repo_idle,
    )
    service.bootstrap()

    # default_idle_gif is only consulted by resolve_action_gif_path, not by
    # bootstrap (which records a gif_id, not a path). Bootstrap with no
    # repo-resolvable fallback emits None.
    _, _, gif_id = state_service.ensure_calls[0]
    assert gif_id is None


# ─── resolve_action_gif_path ──────────────────────────────────────


def test_resolve_returns_user_bound_path_when_available(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()
    user_gif = storage / "click" / "user.gif"
    user_gif.parent.mkdir(parents=True)
    user_gif.write_bytes(b"gif")

    repo = FakeActionRepository([
        ActionEntry(key=CLICK_ACTION_KEY, display_name="Click",
                    gif_id="click/user.gif", is_builtin=True),
    ])
    gif_repo = FakeGifRepository(storage, files={"click/user.gif": user_gif})
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)

    assert service.resolve_action_gif_path("click") == user_gif


def test_resolve_falls_back_to_stand_random(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()
    stand_pick = storage / "stand" / "stand_1.gif"
    stand_pick.parent.mkdir(parents=True)
    stand_pick.write_bytes(b"gif")

    repo = FakeActionRepository()  # no user gif_id
    repo.load()
    gif_repo = FakeGifRepository(storage)
    gif_repo._random_gif_for_state["stand"] = stand_pick
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)

    assert service.resolve_action_gif_path() == stand_pick


def test_resolve_falls_back_to_default_idle_when_nothing_else_works(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()
    fallback_idle = tmp_path / "fallback_idle.gif"
    fallback_idle.write_bytes(b"gif")

    repo = FakeActionRepository()
    repo.load()
    gif_repo = FakeGifRepository(storage)  # nothing exists
    state_service = RecordingStateService()

    service = ActionService(
        repo, state_service, gif_repo, default_idle_gif=fallback_idle,
    )

    assert service.resolve_action_gif_path() == fallback_idle


def test_resolve_returns_none_when_no_asset_path_works(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()

    repo = FakeActionRepository()
    repo.load()
    gif_repo = FakeGifRepository(storage)
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    assert service.resolve_action_gif_path() is None


# ─── bind_click_gif ───────────────────────────────────────────────


def test_bind_click_gif_writes_to_repo_and_state(tmp_path):
    storage = tmp_path / "state"
    storage.mkdir()
    source = tmp_path / "new_click.gif"
    source.write_bytes(b"gif")

    repo = FakeActionRepository()
    repo.load()
    gif_repo = FakeGifRepository(storage)
    state_service = RecordingStateService()
    state_service.store_returns = "click_action/new_click.gif"

    service = ActionService(repo, state_service, gif_repo)
    assert service.bind_click_gif(source) is True

    # ActionRepository has the new gif_id
    assert repo.get(CLICK_ACTION_KEY).gif_id == "click_action/new_click.gif"
    # State got updated as well so next set_state renders it.
    assert (CLICK_ACTION_STATE_KEY, {"gif_id": "click_action/new_click.gif"}) \
        in state_service.update_calls


def test_bind_click_gif_returns_false_when_source_missing(tmp_path):
    repo = FakeActionRepository()
    repo.load()
    gif_repo = FakeGifRepository(tmp_path)
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)

    assert service.bind_click_gif(tmp_path / "does_not_exist.gif") is False
    # No write happened.
    assert repo.get(CLICK_ACTION_KEY).gif_id is None


def test_bind_click_gif_aborts_when_state_store_fails(tmp_path):
    """If StateService.store_gif refuses, ActionRepository must not be touched."""
    storage = tmp_path / "state"
    storage.mkdir()
    source = tmp_path / "click.gif"
    source.write_bytes(b"gif")

    repo = FakeActionRepository()
    repo.load()
    gif_repo = FakeGifRepository(storage)
    state_service = RecordingStateService()
    state_service.store_returns = None  # simulate failure

    service = ActionService(repo, state_service, gif_repo)
    assert service.bind_click_gif(source) is False
    assert repo.get(CLICK_ACTION_KEY).gif_id is None


def test_unbind_click_gif_clears_both_repo_and_state(tmp_path):
    repo = FakeActionRepository([
        ActionEntry(key=CLICK_ACTION_KEY, display_name="Click",
                    gif_id="x.gif", is_builtin=True),
    ])
    gif_repo = FakeGifRepository(tmp_path)
    state_service = RecordingStateService()

    service = ActionService(repo, state_service, gif_repo)
    assert service.unbind_click_gif() is True
    assert repo.get(CLICK_ACTION_KEY).gif_id is None
    assert (CLICK_ACTION_STATE_KEY, {"gif_id": None}) in state_service.update_calls
