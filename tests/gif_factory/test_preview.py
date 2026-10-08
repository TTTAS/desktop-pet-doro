"""預覽小工具測試(純圖像邏輯)。"""

import numpy as np
import pytest
from PIL import Image

from doro_app.core.gif_factory.preview import composite_on_checker, fit_within, middle_frame


def test_middle_frame_picks_center():
    frames = [Image.new("RGBA", (4, 4), (i, 0, 0, 255)) for i in range(5)]
    assert middle_frame(frames).getpixel((0, 0))[0] == 2


def test_middle_frame_empty_raises():
    with pytest.raises(ValueError):
        middle_frame([])


def test_composite_removes_transparency():
    transparent = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    result = composite_on_checker(transparent)

    # 疊到棋盤格後,不該再有全透明像素(透明處露出棋盤底)。
    assert result.mode == "RGBA"
    assert np.array(result)[:, :, 3].min() == 255


def test_fit_within_scales_down_and_reports_ratio():
    image = Image.new("RGBA", (800, 400))
    resized, scale = fit_within(image, 200)

    assert max(resized.size) <= 200
    assert scale == pytest.approx(0.25)


def test_fit_within_does_not_upscale():
    image = Image.new("RGBA", (50, 50))
    resized, scale = fit_within(image, 200)

    assert resized.size == (50, 50)
    assert scale == 1.0
