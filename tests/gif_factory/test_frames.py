"""接縫 2 測試:拆影格。"""

import pytest
from PIL import Image

from doro_app.core.gif_factory import extract_frames


def test_extracts_frames_from_real_video(video_path):
    result = extract_frames(video_path)

    assert len(result.frames) > 0
    assert all(isinstance(f, Image.Image) for f in result.frames)


def test_frame_size_matches_video(video_path):
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()

    result = extract_frames(video_path)

    assert result.frames[0].size == (width, height)


def test_reads_reasonable_fps(video_path):
    result = extract_frames(video_path)

    assert result.fps > 0
    assert result.fps < 240  # 合理範圍,不會是垃圾值


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_frames(tmp_path / "does_not_exist.mp4")


def test_non_video_file_raises(tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"this is not a video")

    with pytest.raises(ValueError):
        extract_frames(bad)
