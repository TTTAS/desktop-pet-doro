"""接縫 1 — 去背引擎(最重要的一塊)。

對外只有一個函式 remove_background(image, options),AI 去背與顏色去背都藏在
它後面,由 options.mode 分派。兩種模式輸出後套用同一個「邊緣內縮(erode)」步驟,
專門吃掉殘留白邊。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

# rembg 的 session 建立一次就好(第一次會下載 isnet-anime 模型,數百 MB)。
# 視窗會用多個背景執行緒跑預覽/整支處理,用鎖確保 session 只被建立一次。
_ai_session = None
_ai_session_lock = threading.Lock()


@dataclass
class MattingOptions:
    """去背設定。所有模式共用一組設定,用 mode 決定走哪條路。"""

    mode: str = "ai"  # "ai" 或 "color"

    # AI 模式(rembg + isnet-anime)
    alpha_matting: bool = False
    alpha_matting_foreground_threshold: int = 240
    alpha_matting_background_threshold: int = 10

    # 顏色去背模式
    color_key: tuple[int, int, int] | None = None
    tolerance: int = 30

    # 兩種模式共用的最後一步:邊緣往內縮幾個像素(吃掉殘渣)
    erode: int = 0


def remove_background(image: Image.Image, options: MattingOptions | None = None) -> Image.Image:
    """輸入一張圖與一組設定,回傳帶透明的 RGBA 圖。"""
    options = options or MattingOptions()

    if options.mode == "ai":
        rgba = _remove_ai(image, options)
    elif options.mode == "color":
        rgba = _remove_color(image, options)
    else:
        raise ValueError(f"未知的去背模式:{options.mode!r}(只能是 'ai' 或 'color')")

    if options.erode > 0:
        rgba = _erode_alpha(rgba, options.erode)

    return rgba


def _get_ai_session():
    """取得(必要時建立)rembg 的 isnet-anime session。延遲載入,避免一 import 就下載。"""
    global _ai_session
    if _ai_session is None:
        with _ai_session_lock:
            # 進鎖後再檢查一次:可能已有另一個執行緒先建好了。
            if _ai_session is None:
                from rembg import new_session

                _ai_session = new_session("isnet-anime")
    return _ai_session


def _remove_ai(image: Image.Image, options: MattingOptions) -> Image.Image:
    from rembg import remove

    session = _get_ai_session()
    result = remove(
        image.convert("RGBA"),
        session=session,
        alpha_matting=options.alpha_matting,
        alpha_matting_foreground_threshold=options.alpha_matting_foreground_threshold,
        alpha_matting_background_threshold=options.alpha_matting_background_threshold,
    )
    return result.convert("RGBA")


def _remove_color(image: Image.Image, options: MattingOptions) -> Image.Image:
    if options.color_key is None:
        raise ValueError("顏色去背模式需要指定要挖掉的顏色(color_key)")

    rgba = np.array(image.convert("RGBA"))
    # 用 int32 才不會在平方時溢位(255**2 = 65025 已超過 int16 上限)。
    rgb = rgba[:, :, :3].astype(np.int32)
    target = np.array(options.color_key, dtype=np.int32)

    # 每個像素跟目標色的歐氏距離,距離在容差內的挖成透明。
    distance = np.sqrt(((rgb - target) ** 2).sum(axis=2))
    mask = distance <= options.tolerance
    rgba[mask, 3] = 0

    return Image.fromarray(rgba, "RGBA")


def _erode_alpha(image: Image.Image, amount: int) -> Image.Image:
    """把 alpha 邊緣往內縮 amount 個像素,不透明區域縮小 → 透明區域變大。"""
    rgba = np.array(image.convert("RGBA"))
    kernel = np.ones((3, 3), np.uint8)
    rgba[:, :, 3] = cv2.erode(rgba[:, :, 3], kernel, iterations=amount)
    return Image.fromarray(rgba, "RGBA")
