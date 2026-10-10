"""接縫 1 測試(02 號):去背變可調 — 邊緣內縮 + 柔化。

邊緣內縮與顏色去背的測試用合成圖,快速又不需下載模型。
柔化(alpha matting)需要 AI,標記為 slow。
"""

import numpy as np
import pytest
from PIL import Image

from doro_app.core.gif_factory import MattingOptions, remove_background


def _transparent_pixel_count(rgba: Image.Image) -> int:
    return int((np.array(rgba)[:, :, 3] == 0).sum())


def _solid_square_on_transparent(size=40, square=20):
    """中間一塊不透明方塊,四周透明。用來測邊緣內縮。"""
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    lo = (size - square) // 2
    hi = lo + square
    arr[lo:hi, lo:hi] = (255, 255, 255, 255)
    return Image.fromarray(arr, "RGBA")


def test_erode_grows_transparent_area():
    image = _solid_square_on_transparent()

    small = remove_background(
        image, MattingOptions(mode="color", color_key=(0, 0, 0), tolerance=0, erode=0)
    )
    big = remove_background(
        image, MattingOptions(mode="color", color_key=(0, 0, 0), tolerance=0, erode=3)
    )

    # 內縮值調大 → 不透明區域被啃掉一圈 → 透明像素變多。
    assert _transparent_pixel_count(big) > _transparent_pixel_count(small)


@pytest.mark.slow
def test_alpha_matting_produces_soft_edges(frame_image):
    soft = remove_background(frame_image, MattingOptions(mode="ai", alpha_matting=True))

    a = np.array(soft)[:, :, 3]
    semi_transparent = int(((a > 0) & (a < 255)).sum())

    # 柔化開啟時,邊緣應有半透明過渡像素(不是非黑即白的硬邊)。
    assert semi_transparent > 0
