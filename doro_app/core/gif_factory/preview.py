"""預覽用的小工具:取中間影格、把透明圖疊在棋盤格上讓透明看得見。

這些是純圖像邏輯(不碰 Tkinter),方便測試與重用。
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def middle_frame(frames: list[Image.Image]) -> Image.Image:
    """取一串影格的中間那張(預覽用)。"""
    if not frames:
        raise ValueError("沒有影格可以預覽")
    return frames[len(frames) // 2]


def composite_on_checker(image: Image.Image, cell: int = 8) -> Image.Image:
    """把 RGBA 圖疊在灰白棋盤格底上,讓半透明/透明區域在預覽裡看得出來。"""
    image = image.convert("RGBA")
    width, height = image.size

    # 用 numpy 向量化畫棋盤格(避免逐像素 Python 迴圈,預覽才跟得上滑桿)。
    ys, xs = np.mgrid[0:height, 0:width]
    dark_mask = (xs // cell + ys // cell) % 2 == 0

    board = np.full((height, width, 4), 255, dtype=np.uint8)
    board[dark_mask, :3] = 200

    checker = Image.fromarray(board, "RGBA")
    return Image.alpha_composite(checker, image)


def fit_within(image: Image.Image, max_size: int) -> tuple[Image.Image, float]:
    """等比縮到能塞進 max_size 見方,回傳(縮圖, 縮放比例)。

    縮放比例讓呼叫端能把「顯示座標」換回「原圖座標」(滴管取色要用)。
    """
    width, height = image.size
    scale = min(max_size / width, max_size / height, 1.0)
    if scale >= 1.0:
        return image, 1.0
    resized = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.NEAREST)
    return resized, scale


def overlay_doro_reference(
    image: Image.Image,
    reference: Image.Image | None,
    foot_y: int,
    opacity: float = 0.35,
    reference_scale: float = 1.0,
) -> Image.Image:
    """在已擺好版面的預覽上疊一層半透明的 Doro 與腳底虛線,方便比對大小。

    image 與 reference 都應是同一個畫布尺寸;reference 為 None 時只畫腳底線。
    reference_scale 以腳底中點為基準縮放參考 Doro,讓它和所選身高一致
    (例如身高 120、參考站姿 167 時傳 120/167)。
    """
    result = image.convert("RGBA").copy()
    if reference is not None:
        ghost = reference.convert("RGBA").resize(result.size, Image.NEAREST)
        if reference_scale != 1.0:
            width, height = result.size
            scaled = ghost.resize(
                (max(1, round(width * reference_scale)), max(1, round(height * reference_scale))),
                Image.LANCZOS,
            )
            ghost = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ghost.paste(
                scaled,
                (round((width - scaled.width) / 2), round(foot_y - foot_y * reference_scale)),
            )
        alpha = ghost.getchannel("A").point(lambda a: round(a * opacity))
        ghost.putalpha(alpha)
        result = Image.alpha_composite(ghost, result)

    pixels = result.load()
    y = min(max(foot_y, 0), result.height - 1)
    for x in range(0, result.width, 6):
        for dx in range(3):
            if x + dx < result.width:
                pixels[x + dx, y] = (230, 60, 60, 255)
    return result
