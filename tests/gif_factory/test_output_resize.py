"""輸出縮圖測試:把成品縮到指定尺寸(接縫 3 的新選項)。"""

import numpy as np
import pytest
from PIL import Image

from doro_app.core.gif_factory import resize_to_fit, save_animation


def _frames(n=3, size=(1024, 1024)):
    # 每張整體顏色不同,縮圖後仍明顯不同(避免被去重合併)。
    return [Image.new("RGBA", size, (60 * i, 0, 0, 255)) for i in range(n)]


def test_resize_square_to_target():
    out = resize_to_fit(Image.new("RGBA", (1024, 1024)), 200)
    assert out.size == (200, 200)


def test_resize_preserves_aspect_ratio():
    out = resize_to_fit(Image.new("RGBA", (400, 200)), 200)
    assert out.size == (200, 100)  # 長邊縮到 200,比例不變


def test_resize_does_not_upscale():
    out = resize_to_fit(Image.new("RGBA", (100, 100)), 200)
    assert out.size == (100, 100)  # 來源比較小,不放大


def test_resize_keeps_transparency():
    src = Image.new("RGBA", (400, 400), (255, 0, 0, 0))  # 全透明
    out = resize_to_fit(src, 200)
    assert out.mode == "RGBA"
    assert np.array(out)[:, :, 3].max() == 0


def test_resize_rejects_nonpositive():
    with pytest.raises(ValueError):
        resize_to_fit(Image.new("RGBA", (10, 10)), 0)


def test_save_animation_with_size_shrinks_output(tmp_path):
    path = save_animation(_frames(), "webp", tmp_path / "out.webp", fps=12, size=200)
    with Image.open(path) as img:
        assert img.size == (200, 200)
        assert getattr(img, "n_frames", 1) == 3


def test_save_animation_without_size_keeps_original(tmp_path):
    path = save_animation(_frames(size=(320, 320)), "webp", tmp_path / "out.webp", fps=12)
    with Image.open(path) as img:
        assert img.size == (320, 320)
