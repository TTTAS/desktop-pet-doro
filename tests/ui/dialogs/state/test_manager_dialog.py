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
