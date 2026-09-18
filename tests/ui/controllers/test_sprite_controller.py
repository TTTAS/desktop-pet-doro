"""Tests for SpriteController — GIF QMovie handle lifecycle."""

from __future__ import annotations

import base64

from doro_app.ui.controllers.sprite_controller import SpriteController
from doro_app.ui.viewmodels.doro_viewmodel import DoroViewModel

# A real (43-byte) 1x1 transparent GIF89a, so QMovie treats it as valid and
# actually opens the file.
_GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def test_switching_sprite_releases_previous_movie(qtbot, tmp_path):
    """Loading a new sprite must free the previously displayed QMovie instead
    of accumulating it. Otherwise every state shown this session keeps its GIF
    file open — a memory leak, and on Windows the file stays locked so it can
    no longer be edited or deleted (WinError 32) even after switching away.
    """
    gif_a = tmp_path / "a.gif"
    gif_b = tmp_path / "b.gif"
    gif_a.write_bytes(_GIF_BYTES)
    gif_b.write_bytes(_GIF_BYTES)

    controller = SpriteController(DoroViewModel())

    assert controller.load_sprite(gif_a) is True
    assert controller._gif_player.count() == 1

    assert controller.load_sprite(gif_b) is True
    # The previous movie must have been released — only the current one is held.
    assert controller._gif_player.count() == 1
