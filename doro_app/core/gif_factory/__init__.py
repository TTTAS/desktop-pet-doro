"""GIF 工廠 — 把 ComfyUI 出的 mp4 就地轉成去背好的動畫檔。

三個純函式核心接縫:
- extract_frames  (frames.py)   影片 → 一張張影格 + FPS
- remove_background (matting.py) 一張圖 + 設定 → 帶透明的 RGBA 圖
- save_animation  (output.py)    多張影格 → WebP / APNG 動畫檔
"""

from doro_app.core.gif_factory.frames import ExtractedVideo, extract_frames
from doro_app.core.gif_factory.matting import MattingOptions, remove_background
from doro_app.core.gif_factory.output import resize_to_fit, save_animation, save_image
from doro_app.core.gif_factory.pipeline import process_video, process_videos

__all__ = [
    "ExtractedVideo",
    "MattingOptions",
    "extract_frames",
    "process_video",
    "process_videos",
    "remove_background",
    "resize_to_fit",
    "save_animation",
    "save_image",
]
