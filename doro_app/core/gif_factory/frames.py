"""接縫 2 — 拆影格。

用 OpenCV(pip 安裝時自帶 ffmpeg)把影片讀成一張張影格,不依賴系統 ffmpeg。
同時取得來源 FPS,供輸出沿用。

網路上抓的動圖(GIF / WebP / APNG)改用 Pillow 讀:逐格合成成完整畫面、保留
原本的透明,並記下每一格各自的顯示時間(GIF 常常每格長短不一)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

import cv2
import numpy as np
from PIL import Image, ImageSequence, UnidentifiedImageError

# 讀不到 FPS 時的保底值(少數影片沒寫 FPS metadata)。
_FALLBACK_FPS = 12.0

# 這些副檔名當成動圖,用 Pillow 讀;其餘交給 OpenCV 當影片讀。
ANIMATED_IMAGE_SUFFIXES = frozenset({".gif", ".webp", ".apng", ".png"})

# 瀏覽器把 0~10 毫秒的 GIF 影格一律當 100 毫秒播,這裡比照,免得動畫快到看不見。
# 只套用在 GIF;WebP / APNG 的短影格(例如 60 fps 的 16 毫秒)是真的,原樣保留,
# 只有沒寫時間(0)時才用預設值。
_GIF_MAX_IGNORED_MS = 10
_DEFAULT_FRAME_MS = 100


def _frame_duration_ms(raw, is_gif: bool) -> int:
    ms = int(raw or 0)
    if ms <= 0 or (is_gif and ms <= _GIF_MAX_IGNORED_MS):
        return _DEFAULT_FRAME_MS
    return ms


@dataclass
class ExtractedVideo:
    """拆影格的結果:一串影格,加上來源 FPS。"""

    frames: list[Image.Image]
    fps: float
    # 每格各自的顯示毫秒數;影片為 None(固定用 fps)。
    durations: list[int] | None = None


def is_animated_image(path: str | Path) -> bool:
    """依副檔名判斷是不是動圖(GIF / WebP / APNG / PNG),而非影片。"""
    return Path(path).suffix.lower() in ANIMATED_IMAGE_SUFFIXES


def extract_frames(video_path: str | Path, cancel: Event | None = None) -> ExtractedVideo:
    """把影片拆成一串 RGB 影格,並回報來源 FPS。

    壞檔 / 非影片 / 空影片都會丟出清楚的錯誤,讓視窗層能顯示給使用者。
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到影片檔:{path}")
    if is_animated_image(path):
        return _extract_image_frames(path, cancel)

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"無法開啟這個檔案,可能不是影片或格式不支援:{path}")

    fps = capture.get(cv2.CAP_PROP_FPS)

    frames: list[Image.Image] = []
    try:
        while True:
            if cancel is not None and cancel.is_set():
                from .pipeline import ProcessingCancelled

                raise ProcessingCancelled("已取消讀取")
            ok, bgr = capture.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(np.asarray(rgb)))
    finally:
        capture.release()

    if not frames:
        raise ValueError(f"這個檔案讀不到任何影格,可能不是有效的影片:{path}")

    if not fps or fps <= 0:
        fps = _FALLBACK_FPS

    return ExtractedVideo(frames=frames, fps=float(fps))


def _extract_image_frames(path: Path, cancel: Event | None) -> ExtractedVideo:
    """把動圖拆成完整合成過的 RGBA 影格,保留透明與每格時間。"""
    from .pipeline import check_cancelled

    try:
        source = Image.open(path)
    except (UnidentifiedImageError, OSError) as err:
        raise ValueError(f"無法開啟這個檔案,可能不是圖片或格式不支援:{path}") from err

    frames: list[Image.Image] = []
    durations: list[int] = []
    is_gif = source.format == "GIF"
    with source:
        # Pillow 逐格 seek 時會依 disposal 合成,轉 RGBA 就是畫面上看到的那一格。
        for frame in ImageSequence.Iterator(source):
            check_cancelled(cancel)
            frames.append(frame.convert("RGBA"))
            durations.append(_frame_duration_ms(frame.info.get("duration"), is_gif))

    if not frames:
        raise ValueError(f"這個檔案讀不到任何影格:{path}")

    fps = 1000.0 * len(durations) / sum(durations)
    return ExtractedVideo(frames=frames, fps=fps, durations=durations)
