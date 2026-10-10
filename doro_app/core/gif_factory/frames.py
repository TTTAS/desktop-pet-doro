"""接縫 2 — 拆影格。

用 OpenCV(pip 安裝時自帶 ffmpeg)把影片讀成一張張影格,不依賴系統 ffmpeg。
同時取得來源 FPS,供輸出沿用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

import cv2
import numpy as np
from PIL import Image

# 讀不到 FPS 時的保底值(少數影片沒寫 FPS metadata)。
_FALLBACK_FPS = 12.0


@dataclass
class ExtractedVideo:
    """拆影格的結果:一串影格,加上來源 FPS。"""

    frames: list[Image.Image]
    fps: float


def extract_frames(video_path: str | Path, cancel: Event | None = None) -> ExtractedVideo:
    """把影片拆成一串 RGB 影格,並回報來源 FPS。

    壞檔 / 非影片 / 空影片都會丟出清楚的錯誤,讓視窗層能顯示給使用者。
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到影片檔:{path}")

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
