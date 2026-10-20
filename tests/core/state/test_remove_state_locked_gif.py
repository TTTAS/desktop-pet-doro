"""Removing a state whose GIF is still open (Windows WinError 32).

Reported: the removal raised, the state vanished from memory but stayed in the
saved config (it came back after restarting Doro) and the manager never refreshed.
"""

from pathlib import Path

import pytest
from PIL import Image

from doro_app.core.exceptions import GifStorageError
from doro_app.core.state import GifRepository, StateRepository


@pytest.fixture
def locked(monkeypatch):
    """Paths in this set behave like files another program holds open on Windows."""
    paths: set[Path] = set()
    real_unlink = Path.unlink

    def unlink(self, *args, **kwargs):
        if self in paths:
            raise PermissionError(32, "The process cannot access the file", str(self))
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    return paths


@pytest.fixture
def gif(tmp_path):
    path = tmp_path / "source.gif"
    Image.new("RGB", (8, 8), "red").save(path)
    return path


def test_locked_gif_still_removes_and_persists_the_state(real_state_service, gif, locked):
    service = real_state_service
    service.add_state("xx", "XX")
    assert service.add_gif("xx", gif)
    locked.update(service._gif_repo.storage_dir.rglob("xx*"))

    assert service.remove_state("xx") is True

    assert service.get_state("xx") is None
    assert "xx" not in StateRepository(service._state_repo.config_path).load_all()
    assert "xx" in service.pending_gif_deletions

    locked.clear()  # the preview released the file
    service.retry_pending_gif_deletions()
    assert service.pending_gif_deletions == frozenset()
    assert not list(service._gif_repo.storage_dir.rglob("xx*"))


def test_removing_the_current_state_switches_doro_away_first(real_state_service):
    service = real_state_service
    service.add_state("rest", "Rest")
    service.add_state("xx", "XX")
    service.set_state("xx", force=True)

    assert service.remove_state("xx") is True
    assert service.get_current_state_key() in ("idle", "rest")


def test_recreating_a_state_does_not_inherit_leftover_gifs(real_state_service, gif, locked):
    service = real_state_service
    service.add_state("xx", "XX")
    assert service.add_gif("xx", gif)
    locked.update(service._gif_repo.storage_dir.rglob("xx*"))
    service.remove_state("xx")
    locked.clear()

    service.add_state("xx", "XX again")

    assert not list(service._gif_repo.storage_dir.rglob("xx*.gif"))
    assert "xx" not in service.pending_gif_deletions


def test_protected_state_is_still_refused(real_state_service):
    assert real_state_service.remove_state("idle") is False


def test_delete_all_gifs_tries_every_file_then_reports(tmp_path, locked):
    (tmp_path / "xx.gif").touch()
    state_dir = tmp_path / "xx"
    state_dir.mkdir()
    (state_dir / "xx_1.gif").touch()
    (state_dir / "xx_2.gif").touch()
    locked.add(state_dir / "xx_1.gif")

    with pytest.raises(GifStorageError, match="xx_1.gif"):
        GifRepository(tmp_path).delete_all_gifs("xx")

    assert not (tmp_path / "xx.gif").exists()
    assert not (state_dir / "xx_2.gif").exists()
    assert (state_dir / "xx_1.gif").exists()
