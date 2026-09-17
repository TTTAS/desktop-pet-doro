"""Tests for multi-GIF per state support."""

from pathlib import Path

import pytest

from doro_app.core.state.repository import GifRepository
from doro_app.core.exceptions import GifNotFoundError

# ═══════════════════════════════════════════════════════════
# GifRepository — multi-GIF operations
# ═══════════════════════════════════════════════════════════


class TestGifRepositoryListGifs:
    """Test listing GIFs from a state's subfolder."""

    def test_list_gifs_returns_sorted_paths(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_2.gif").touch()
        (state_dir / "stand_1.gif").touch()
        (state_dir / "stand_3.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.list_gifs("stand")

        assert len(result) == 3
        assert result[0].name == "stand_1.gif"
        assert result[1].name == "stand_2.gif"
        assert result[2].name == "stand_3.gif"

    def test_list_gifs_ignores_non_gif_files(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()
        (state_dir / "readme.txt").touch()
        (state_dir / "notes.png").touch()

        repo = GifRepository(tmp_path)
        result = repo.list_gifs("stand")

        assert len(result) == 1
        assert result[0].name == "stand_1.gif"

    def test_list_gifs_empty_subfolder(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()

        repo = GifRepository(tmp_path)
        assert repo.list_gifs("stand") == []

    def test_list_gifs_no_subfolder(self, tmp_path):
        repo = GifRepository(tmp_path)
        assert repo.list_gifs("stand") == []

    def test_list_gifs_case_insensitive_extension(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.GIF").touch()
        (state_dir / "stand_2.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.list_gifs("stand")
        assert len(result) == 2


class TestGifRepositoryPickRandomGif:
    """Test random GIF selection."""

    def test_pick_random_from_subfolder(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()
        (state_dir / "stand_2.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.pick_random_gif("stand")

        assert result is not None
        assert result.suffix.lower() == ".gif"
        assert result.parent == state_dir

    def test_pick_random_fallback_to_single_file(self, tmp_path):
        (tmp_path / "stand.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.pick_random_gif("stand")

        assert result == tmp_path / "stand.gif"

    def test_pick_random_subfolder_priority_over_single_file(self, tmp_path):
        # Both exist — subfolder should win
        (tmp_path / "stand.gif").touch()
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.pick_random_gif("stand")

        assert result.parent == state_dir

    def test_pick_random_no_gif(self, tmp_path):
        repo = GifRepository(tmp_path)
        assert repo.pick_random_gif("stand") is None

    def test_pick_random_empty_subfolder_fallback(self, tmp_path):
        # Empty subfolder + single file → should use single file
        (tmp_path / "stand").mkdir()
        (tmp_path / "stand.gif").touch()

        repo = GifRepository(tmp_path)
        result = repo.pick_random_gif("stand")
        assert result == tmp_path / "stand.gif"


class TestGifRepositoryAddGif:
    """Test adding GIFs to a state's subfolder."""

    def test_add_gif_creates_subfolder(self, tmp_path):
        source = tmp_path / "my_gif.gif"
        source.write_bytes(b"GIF89a")

        repo = GifRepository(tmp_path)
        resource_id = repo.add_gif(source, "stand")

        assert (tmp_path / "stand").is_dir()
        # Normalize separators so the assertion holds on Windows (\) too.
        assert "stand/" in resource_id.replace("\\", "/")
        assert resource_id.endswith(".gif")

    def test_add_gif_sequential_naming(self, tmp_path):
        source = tmp_path / "my_gif.gif"
        source.write_bytes(b"GIF89a")

        repo = GifRepository(tmp_path)
        id1 = repo.add_gif(source, "stand")
        id2 = repo.add_gif(source, "stand")

        assert "stand_1.gif" in id1
        assert "stand_2.gif" in id2

    def test_add_gif_copies_file(self, tmp_path):
        source = tmp_path / "my_gif.gif"
        source.write_bytes(b"GIF89a_test_data")

        repo = GifRepository(tmp_path)
        repo.add_gif(source, "stand")

        copied = tmp_path / "stand" / "stand_1.gif"
        assert copied.exists()
        assert copied.read_bytes() == b"GIF89a_test_data"

    def test_add_gif_migrates_single_file(self, tmp_path):
        """When single-file exists, add_gif migrates it into subfolder first."""
        # Setup: existing single-file GIF
        single_file = tmp_path / "stand.gif"
        single_file.write_bytes(b"GIF89a_original")

        # Add a new GIF
        new_source = tmp_path / "new.gif"
        new_source.write_bytes(b"GIF89a_new")

        repo = GifRepository(tmp_path)
        resource_id = repo.add_gif(new_source, "stand")

        # Single file should be gone (migrated)
        assert not single_file.exists()

        # Subfolder should have 2 files
        state_dir = tmp_path / "stand"
        assert state_dir.is_dir()
        gifs = repo.list_gifs("stand")
        assert len(gifs) == 2

        # First file is the migrated original
        assert gifs[0].name == "stand_1.gif"
        assert gifs[0].read_bytes() == b"GIF89a_original"

        # Second file is the newly added
        assert gifs[1].name == "stand_2.gif"
        assert gifs[1].read_bytes() == b"GIF89a_new"

        # Resource ID points to the new file
        assert "stand_2.gif" in resource_id

    def test_add_gif_no_migration_when_subfolder_exists(self, tmp_path):
        """If subfolder already has files, don't migrate single file again."""
        # Setup: both single file and subfolder exist
        (tmp_path / "stand.gif").write_bytes(b"single")
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").write_bytes(b"existing")

        new_source = tmp_path / "new.gif"
        new_source.write_bytes(b"new")

        repo = GifRepository(tmp_path)
        repo.add_gif(new_source, "stand")

        # Single file should still be there (not migrated — subfolder wasn't empty)
        assert (tmp_path / "stand.gif").exists()
        # Subfolder should have 2 files (existing + new)
        gifs = repo.list_gifs("stand")
        assert len(gifs) == 2

    def test_add_gif_source_not_found(self, tmp_path):
        repo = GifRepository(tmp_path)
        with pytest.raises(GifNotFoundError):
            repo.add_gif(tmp_path / "nonexistent.gif", "stand")


class TestGifRepositoryRemoveGif:
    """Test removing individual GIFs from a subfolder."""

    def test_remove_gif_deletes_file(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        target = state_dir / "stand_1.gif"
        target.touch()
        (state_dir / "stand_2.gif").touch()

        repo = GifRepository(tmp_path)
        assert repo.remove_gif("stand", "stand_1.gif") is True
        assert not target.exists()
        # Subfolder still exists (has stand_2.gif)
        assert state_dir.exists()

    def test_remove_gif_cleans_empty_subfolder(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()

        repo = GifRepository(tmp_path)
        repo.remove_gif("stand", "stand_1.gif")

        assert not state_dir.exists()

    def test_remove_gif_not_found(self, tmp_path):
        repo = GifRepository(tmp_path)
        assert repo.remove_gif("stand", "nonexistent.gif") is False

    def test_remove_gif_blocks_path_traversal(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()

        repo = GifRepository(tmp_path)
        assert repo.remove_gif("stand", "../../../etc/passwd") is False


class TestGifRepositoryDeleteAllGifs:
    """Test full cleanup of all GIFs for a state."""

    def test_delete_all_removes_single_file(self, tmp_path):
        (tmp_path / "stand.gif").touch()

        repo = GifRepository(tmp_path)
        assert repo.delete_all_gifs("stand") is True
        assert not (tmp_path / "stand.gif").exists()

    def test_delete_all_removes_subfolder(self, tmp_path):
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()
        (state_dir / "stand_2.gif").touch()

        repo = GifRepository(tmp_path)
        assert repo.delete_all_gifs("stand") is True
        assert not state_dir.exists()

    def test_delete_all_removes_both(self, tmp_path):
        (tmp_path / "stand.gif").touch()
        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        (state_dir / "stand_1.gif").touch()

        repo = GifRepository(tmp_path)
        assert repo.delete_all_gifs("stand") is True
        assert not (tmp_path / "stand.gif").exists()
        assert not state_dir.exists()

    def test_delete_all_returns_false_when_nothing_exists(self, tmp_path):
        repo = GifRepository(tmp_path)
        assert repo.delete_all_gifs("stand") is False


# ═══════════════════════════════════════════════════════════
# StateService — multi-GIF integration
# ═══════════════════════════════════════════════════════════


class TestStateServiceMultiGif:
    """Test StateService multi-GIF support."""

    def test_get_gif_path_uses_random_pick(self, state_service_with_mocks, mock_gif_repo):
        """get_gif_path prefers multi-GIF subfolder."""
        state_service_with_mocks.add_state("stand", "Stand")
        random_path = Path("/fake/storage/stand/stand_2.gif")
        mock_gif_repo.pick_random_gif.return_value = random_path

        result = state_service_with_mocks.get_gif_path("stand")

        assert result == random_path
        mock_gif_repo.pick_random_gif.assert_called_with("stand")

    def test_get_gif_path_falls_back_to_gif_id(self, state_service_with_mocks, mock_gif_repo):
        """get_gif_path falls back to gif_id when no subfolder."""
        state_service_with_mocks.add_state("stand", "Stand")
        state_service_with_mocks.update_state("stand", gif_id="stand.gif")
        mock_gif_repo.pick_random_gif.return_value = None
        mock_gif_repo.get_path.return_value = Path("/fake/stand.gif")

        result = state_service_with_mocks.get_gif_path("stand")

        assert result == Path("/fake/stand.gif")

    def test_add_gif_delegates_to_manager(self, state_service_with_mocks, mock_gif_repo):
        state_service_with_mocks.add_state("stand", "Stand")
        mock_gif_repo.add_gif.return_value = "stand/stand_1.gif"

        result = state_service_with_mocks.add_gif("stand", Path("/source.gif"))

        assert result is True
        mock_gif_repo.add_gif.assert_called_once()

    def test_add_gif_returns_false_for_missing_state(self, state_service_with_mocks):
        result = state_service_with_mocks.add_gif("nonexistent", Path("/source.gif"))
        assert result is False

    def test_list_gif_paths_delegates(self, state_service_with_mocks, mock_gif_repo):
        paths = [Path("/a.gif"), Path("/b.gif")]
        mock_gif_repo.list_gifs.return_value = paths

        result = state_service_with_mocks.list_gif_paths("stand")
        assert result == paths

    def test_delete_all_gifs_delegates(self, state_service_with_mocks, mock_gif_repo):
        mock_gif_repo.delete_all_gifs.return_value = True

        result = state_service_with_mocks.delete_all_gifs("stand")

        assert result is True
        mock_gif_repo.delete_all_gifs.assert_called_with("stand")


# ═══════════════════════════════════════════════════════════
# Backward compatibility
# ═══════════════════════════════════════════════════════════


class TestBackwardCompat:
    """Verify single-file states still work."""

    def test_single_file_gif_still_loads(self, tmp_path):
        """A state with just {key}.gif (no subfolder) works."""
        (tmp_path / "idle.gif").write_bytes(b"GIF89a")

        repo = GifRepository(tmp_path)
        result = repo.pick_random_gif("idle")

        assert result == tmp_path / "idle.gif"

    def test_store_gif_single_file_unchanged(self, tmp_path):
        """store_gif() still creates single-file {key}.gif."""
        source = tmp_path / "source.gif"
        source.write_bytes(b"GIF89a")

        repo = GifRepository(tmp_path)
        resource_id = repo.store_gif(source, "idle")

        assert resource_id == "idle.gif"
        assert (tmp_path / "idle.gif").exists()

    def test_delete_single_file_unchanged(self, tmp_path):
        """delete() still removes single-file."""
        (tmp_path / "idle.gif").write_bytes(b"GIF89a")

        repo = GifRepository(tmp_path)
        assert repo.delete("idle.gif") is True
        assert not (tmp_path / "idle.gif").exists()
