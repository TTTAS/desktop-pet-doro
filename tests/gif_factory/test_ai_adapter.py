"""Verify the optional rembg adapter without downloading a model."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from doro_app.core.gif_factory import matting


def test_ai_session_is_reused_and_options_reach_rembg(monkeypatch):
    backend = SimpleNamespace(
        new_session=Mock(return_value=object()),
        remove=Mock(return_value=Image.new("RGBA", (8, 8), (255, 0, 0, 128))),
    )
    monkeypatch.setitem(sys.modules, "rembg", backend)
    monkeypatch.setattr(matting, "_ai_session", None)
    options = matting.MattingOptions(alpha_matting=True)
    source = Image.new("RGB", (8, 8))
    for _ in range(2):
        result = matting.remove_background(source, options)
        assert result.getpixel((0, 0))[3] == 128
    backend.new_session.assert_called_once_with("isnet-anime")
    assert backend.remove.call_args.kwargs == {
        "session": backend.new_session.return_value,
        "alpha_matting": True,
        "alpha_matting_foreground_threshold": 240,
        "alpha_matting_background_threshold": 10,
    }
