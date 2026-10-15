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


def _white_body_on_white():
    """白底上一個黑色外框圍住的白色身體(中間 10..30 是身體)。"""
    arr = np.full((40, 40, 4), 255, dtype=np.uint8)
    arr[8:32, 8:32, :3] = 0  # 外框
    arr[10:30, 10:30, :3] = 255  # 外框內的白色身體
    return Image.fromarray(arr, "RGBA")


def test_edge_only_keeps_same_color_inside_the_outline():
    image = _white_body_on_white()
    options = {"mode": "color", "color_key": (255, 255, 255), "tolerance": 30}

    old = np.array(remove_background(image, MattingOptions(**options)))
    edge = np.array(remove_background(image, MattingOptions(**options, edge_only=True)))

    assert old[20, 20, 3] == 0  # 舊行為:身體也被挖掉
    assert edge[20, 20, 3] == 255  # 只挖邊緣相連:身體保留
    assert edge[2, 2, 3] == 0  # 背景照樣透明
    assert edge[9, 9, 3] == 255  # 外框保留


def test_edge_only_does_not_leak_through_diagonal_gaps():
    image = _white_body_on_white()
    arr = np.array(image)
    arr[8, 8, :3] = 255  # 外框角落缺一格,只與內部斜向相連
    result = remove_background(
        Image.fromarray(arr, "RGBA"),
        MattingOptions(mode="color", color_key=(255, 255, 255), tolerance=30, edge_only=True),
    )

    assert np.array(result)[20, 20, 3] == 255


def test_edge_only_on_real_white_bodied_frame(frame_image):
    options = MattingOptions(mode="color", color_key=(255, 255, 255), tolerance=30, edge_only=True)
    result = np.array(remove_background(frame_image, options))

    assert result[2, 2, 3] == 0  # 角落背景透明
    assert result[200, 134, 3] == 255  # 白色身體中央保留
