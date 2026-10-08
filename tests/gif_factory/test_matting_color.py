"""接縫 1 測試(03 號):顏色去背模式。用合成圖,快速且不需 AI 模型。"""

import numpy as np
import pytest
from PIL import Image

from doro_app.core.gif_factory import MattingOptions, remove_background


def _two_color_image():
    """左半綠色(要挖掉的背景),右半紅色(角色主體)。"""
    arr = np.zeros((20, 20, 4), dtype=np.uint8)
    arr[:, :10] = (0, 255, 0, 255)  # 綠
    arr[:, 10:] = (255, 0, 0, 255)  # 紅
    return Image.fromarray(arr, "RGBA")


def test_color_key_makes_target_transparent_and_keeps_rest():
    image = _two_color_image()

    result = remove_background(
        image, MattingOptions(mode="color", color_key=(0, 255, 0), tolerance=20)
    )
    arr = np.array(result)

    assert (arr[:, :10, 3] == 0).all()  # 綠色區被挖成透明
    assert (arr[:, 10:, 3] == 255).all()  # 紅色主體不受影響


def test_larger_tolerance_removes_more():
    # 背景是接近綠、但不完全相同的顏色,測容差擴大能不能吃到它。
    arr = np.zeros((20, 20, 4), dtype=np.uint8)
    arr[:, :10] = (30, 255, 30, 255)  # 略偏的綠
    arr[:, 10:] = (255, 0, 0, 255)
    image = Image.fromarray(arr, "RGBA")

    tight = remove_background(
        image, MattingOptions(mode="color", color_key=(0, 255, 0), tolerance=5)
    )
    loose = remove_background(
        image, MattingOptions(mode="color", color_key=(0, 255, 0), tolerance=60)
    )

    tight_transparent = int((np.array(tight)[:, :, 3] == 0).sum())
    loose_transparent = int((np.array(loose)[:, :, 3] == 0).sum())

    assert loose_transparent > tight_transparent


def test_color_mode_without_color_key_raises():
    with pytest.raises(ValueError):
        remove_background(_two_color_image(), MattingOptions(mode="color"))
