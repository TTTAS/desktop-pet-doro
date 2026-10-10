"""接縫 1 測試:去背(最重要,測最多)。

AI 模式的測試會在第一次跑時下載 isnet-anime 模型(數百 MB,只一次)。
"""

import numpy as np
import pytest

from doro_app.core.gif_factory import MattingOptions, remove_background


def _corner_alphas(rgba):
    arr = np.array(rgba)
    return [
        arr[0, 0, 3],
        arr[0, -1, 3],
        arr[-1, 0, 3],
        arr[-1, -1, 3],
    ]


@pytest.mark.slow
def test_ai_makes_background_transparent(frame_image):
    result = remove_background(frame_image, MattingOptions(mode="ai"))

    assert result.mode == "RGBA"
    # 四個角落屬於背景,去背後應變透明。
    assert max(_corner_alphas(result)) == 0


@pytest.mark.slow
def test_ai_keeps_subject_opaque(frame_image):
    result = remove_background(frame_image, MattingOptions(mode="ai"))

    arr = np.array(result)
    # 角色主體大致在畫面中央,該區至少有一部分仍不透明。
    h, w = arr.shape[:2]
    center = arr[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3, 3]
    assert center.max() > 0
