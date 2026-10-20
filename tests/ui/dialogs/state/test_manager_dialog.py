"""Tests for StateManagerDialog."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

from PySide6 import QtWidgets

import doro_app.ui.dialogs.state.gif_gallery_dialog as gallery_mod

# A real (43-byte) 1x1 transparent GIF89a. It must be valid so the dialog's
# preview QMovie actually opens the file — that open handle is what used to
# block deletion on Windows.
_GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class TestStateManagerDialogEditGif:
    """Regression coverage for GIF removal file-handle release."""

    def test_edit_gif_releases_previews_before_delete(self, qtbot, tmp_path, monkeypatch):
        """The manager's own state cards stream the same GIFs via QMovie, which
        keeps the files open. `_on_edit_gif` must release those handles before
        `remove_gif` unlinks the file, or Windows fails the delete with
        WinError 32 (file in use by another process).
        """
        from doro_app.ui.dialogs.state.manager_dialog import StateManagerDialog

        state_dir = tmp_path / "stand"
        state_dir.mkdir()
        keep = state_dir / "stand_1.gif"
        drop = state_dir / "stand_2.gif"
        keep.write_bytes(_GIF_BYTES)
        drop.write_bytes(_GIF_BYTES)

        state = MagicMock()
        state.label = "Stand"
        state.gif_id = None

        service = MagicMock()
        service.visible_state_keys.return_value = ["stand"]
        service.get_state.return_value = state
        # Reflect the real folder each call, so previews reload correctly after
        # the deletion.
        service.list_gif_paths.side_effect = lambda key: sorted(state_dir.glob("*.gif"))

        def _remove_gif(key, filename):
            # Real unlink — this is exactly the call that raised WinError 32 while
            # a preview QMovie still held the file open.
            (state_dir / filename).unlink()
            return True

        service.remove_gif.side_effect = _remove_gif

        dialog = StateManagerDialog(service)
        qtbot.addWidget(dialog)

        # Fake the gallery: user removed stand_2.gif and clicked OK.
        fake_gallery = MagicMock()
        fake_gallery.exec.return_value = QtWidgets.QDialog.DialogCode.Accepted
        fake_gallery.removed_filenames = ["stand_2.gif"]
        fake_gallery.added_paths = []
        # _on_edit_gif imports GifGalleryDialog from its source module locally,
        # so patch it there.
        monkeypatch.setattr(gallery_mod, "GifGalleryDialog", lambda *a, **k: fake_gallery)

        # Must not raise GifStorageError, and the file must actually be gone.
        dialog._on_edit_gif("stand")

        assert not drop.exists()
        assert keep.exists()
        service.remove_gif.assert_called_once_with("stand", "stand_2.gif")


class TestStateManagerDialogRemoveState:
    """Del on a state card: release previews, refresh, never leave the dialog stale."""

    def _dialog(self, qtbot, tmp_path, service_setup):
        from doro_app.ui.dialogs.state.manager_dialog import StateManagerDialog

        gif = tmp_path / "xx.gif"
        gif.write_bytes(_GIF_BYTES)
        state = MagicMock(label="XX", gif_id=None)
        keys = ["xx"]
        service = MagicMock()
        service.is_state_protected.return_value = False
        service.visible_state_keys.side_effect = lambda: list(keys)
        service.get_state.side_effect = lambda key: state if key in keys else None
        service.list_gif_paths.side_effect = lambda key: [gif] if key in keys else []
        service.pending_gif_deletions = frozenset()
        service_setup(service, keys, gif)
        dialog = StateManagerDialog(service)
        qtbot.addWidget(dialog)
        return dialog, service

    def _confirm(self, monkeypatch):
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "question",
            lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes,
        )

    def test_remove_releases_previews_first_and_refreshes(self, qtbot, tmp_path, monkeypatch):
        open_movies_at_removal = []

        def setup(service, keys, gif):
            def remove_state(key):
                # The card's QMovie used to hold this file open (WinError 32).
                open_movies_at_removal.append(dialog._gif_player.count())
                keys.remove(key)
                gif.unlink()
                return True

            service.remove_state.side_effect = remove_state

        dialog, _ = self._dialog(qtbot, tmp_path, setup)
        assert dialog._gif_player.count() > 0  # the card is playing the GIF
        self._confirm(monkeypatch)

        dialog._on_remove("xx")

        assert open_movies_at_removal == [0]
        assert dialog._cards == []  # refreshed: the card is gone

    def test_errors_are_shown_and_the_grid_still_refreshes(self, qtbot, tmp_path, monkeypatch):
        def setup(service, keys, gif):
            def remove_state(key):
                keys.remove(key)
                raise RuntimeError("disk on fire")

            service.remove_state.side_effect = remove_state

        dialog, _ = self._dialog(qtbot, tmp_path, setup)
        self._confirm(monkeypatch)
        warnings = []
        monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))

        dialog._on_remove("xx")

        assert warnings == ["Failed to remove state: disk on fire"]
        assert dialog._cards == []

    def test_locked_file_is_explained(self, qtbot, tmp_path, monkeypatch):
        def setup(service, keys, gif):
            def remove_state(key):
                keys.remove(key)
                service.pending_gif_deletions = frozenset({key})
                return True

            service.remove_state.side_effect = remove_state

        dialog, _ = self._dialog(qtbot, tmp_path, setup)
        self._confirm(monkeypatch)
        notes = []
        monkeypatch.setattr(
            QtWidgets.QMessageBox, "information", lambda *a, **k: notes.append(a[2])
        )

        dialog._on_remove("xx")

        assert len(notes) == 1 and "仍被其他程式使用中" in notes[0]
