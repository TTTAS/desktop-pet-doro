"""GIF 工廠 — 把 ComfyUI 出的 mp4 或網路上的 GIF 轉成去背好、尺寸一致的動畫檔。

三個純函式核心接縫:
- extract_frames  (frames.py)   影片 / 動圖 → 一張張影格 + FPS(+ 逐格時間)
- remove_background (matting.py) 一張圖 + 設定 → 帶透明的 RGBA 圖
- save_animation  (output.py)    多張影格 → WebP / APNG / GIF 動畫檔
"""

from doro_app.core.gif_factory.frames import ExtractedVideo, extract_frames, is_animated_image
from doro_app.core.gif_factory.matting import MattingOptions, remove_background
from doro_app.core.gif_factory.output import (
    DoroSpec,
    body_bounds,
    fit_to_canvas,
    fit_to_doro,
    resize_to_fit,
    save_animation,
    save_image,
)
from doro_app.core.gif_factory.pipeline import process_video, process_videos

__all__ = [
    "DoroSpec",
    "ExtractedVideo",
    "MattingOptions",
    "body_bounds",
    "extract_frames",
    "fit_to_canvas",
    "fit_to_doro",
    "is_animated_image",
    "process_video",
    "process_videos",
    "remove_background",
    "resize_to_fit",
    "save_animation",
    "save_image",
]
