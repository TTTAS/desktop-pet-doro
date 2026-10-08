from threading import Event

import pytest

from doro_app.core.gif_factory import MattingOptions, process_video, process_videos
from doro_app.core.gif_factory.pipeline import ProcessingCancelled


def test_cancel_does_not_create_output(video_path, tmp_path):
    cancel = Event()
    output = tmp_path / "cancelled.webp"
    with pytest.raises(ProcessingCancelled):
        process_video(
            video_path,
            output,
            options=MattingOptions(mode="color", color_key=(0, 0, 0)),
            cancel=cancel,
            progress=lambda done, total: cancel.set(),
        )
    assert not output.exists()


def test_batch_preserves_existing_and_duplicate_names(video_path, tmp_path):
    old = tmp_path / f"{video_path.stem}.webp"
    old.write_bytes(b"keep me")
    results = process_videos(
        [video_path, video_path],
        tmp_path,
        size=32,
        options=MattingOptions(mode="color", color_key=(0, 0, 0)),
    )
    assert old.read_bytes() == b"keep me"
    assert len(set(results)) == 2
    assert all(path != old and path.is_file() for path in results)
