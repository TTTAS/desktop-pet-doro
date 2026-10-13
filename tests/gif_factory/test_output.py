"""接縫 3 測試:輸出。存檔後讀回來驗證。"""

import pytest
from PIL import Image

from doro_app.core.gif_factory import save_animation


def _make_frames(n=3, color=(255, 0, 0, 128)):
    """做幾張半透明的測試影格,每張略有不同(避免存檔時被去重合併)。"""
    frames = []
    for i in range(n):
        img = Image.new("RGBA", (16, 16), color)
        img.putpixel((i % 16, 0), (0, 255, 0, 255))  # 每張改一個像素
        frames.append(img)
    return frames


@pytest.mark.parametrize("fmt", ["webp", "apng"])
def test_saved_file_exists(tmp_path, fmt):
    path = save_animation(_make_frames(), fmt, tmp_path / f"out.{fmt}", fps=12)
    assert path.exists()
    assert path.stat().st_size > 0


@pytest.mark.parametrize("fmt,pillow_format", [("webp", "WEBP"), ("apng", "PNG")])
def test_saved_file_is_correct_format(tmp_path, fmt, pillow_format):
    path = save_animation(_make_frames(), fmt, tmp_path / f"out.{fmt}", fps=12)

    with Image.open(path) as img:
        assert img.format == pillow_format


@pytest.mark.parametrize("fmt", ["webp", "apng"])
def test_saved_file_is_animated(tmp_path, fmt):
    path = save_animation(_make_frames(n=5), fmt, tmp_path / f"out.{fmt}", fps=12)

    with Image.open(path) as img:
        assert getattr(img, "n_frames", 1) == 5


@pytest.mark.parametrize("fmt", ["webp", "apng"])
def test_saved_file_keeps_transparency(tmp_path, fmt):
    frames = _make_frames(color=(255, 0, 0, 0))  # 全透明
    path = save_animation(frames, fmt, tmp_path / f"out.{fmt}", fps=12)

    with Image.open(path) as img:
        assert img.mode in ("RGBA", "P")
        alpha = img.convert("RGBA").getchannel("A")
        assert alpha.getextrema()[0] == 0  # 有全透明的像素


def test_unsupported_format_raises(tmp_path):
    with pytest.raises(ValueError):
        save_animation(_make_frames(), "bmp", tmp_path / "out.bmp", fps=12)
