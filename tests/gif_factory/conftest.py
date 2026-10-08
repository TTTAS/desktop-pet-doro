"""共用測試素材(fixtures)。用真實的 doro 影格與 ComfyUI 影片。"""

from pathlib import Path

import pytest

pytest.importorskip("cv2")
pytest.importorskip("PIL")
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def frame_path() -> Path:
    """一張真實影格:白身體角色 + 淺色背景。"""
    return FIXTURES / "frame_25_delay-0.png"


@pytest.fixture
def frame_image(frame_path: Path) -> Image.Image:
    return Image.open(frame_path).convert("RGBA")


@pytest.fixture
def video_path() -> Path:
    """一支真實的 ComfyUI 輸出影片。"""
    return FIXTURES / "ComfyUI_00012_.mp4"
