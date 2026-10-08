"""批量處理測試:process_videos(多支影片 → 每支各出一個檔)。

用顏色去背模式(不需下載 AI 模型),讓這批測試維持快速。
"""

import pytest

from doro_app.core.gif_factory import MattingOptions, process_videos


def _color_options() -> MattingOptions:
    # 隨便挖一個顏色即可,這裡只驗「批量流程」跑通、輸出正確,不驗去背品質。
    return MattingOptions(mode="color", color_key=(0, 0, 0), tolerance=10)


def test_process_videos_outputs_one_file_per_input(tmp_path, video_path):
    outputs = process_videos(
        [video_path, video_path],
        tmp_path,
        fmt="webp",
        options=_color_options(),
        size=64,
    )
    assert len(outputs) == 2
    for out in outputs:
        assert out.exists()
        assert out.stat().st_size > 0


def test_process_videos_names_output_after_input_stem(tmp_path, video_path):
    (out,) = process_videos(
        [video_path],
        tmp_path,
        fmt="webp",
        options=_color_options(),
        size=64,
    )
    assert out.name == f"{video_path.stem}.webp"
    assert out.parent == tmp_path


def test_process_videos_reports_progress(tmp_path, video_path):
    seen: list[tuple[int, int]] = []

    def on_progress(file_index, file_total, done, total, name):
        seen.append((file_index, file_total))

    process_videos(
        [video_path, video_path],
        tmp_path,
        fmt="webp",
        options=_color_options(),
        size=64,
        on_progress=on_progress,
    )
    # 兩支都回報過,且回報的 file_total 一律是 2。
    assert {fi for fi, _ in seen} == {1, 2}
    assert all(ft == 2 for _, ft in seen)


def test_process_videos_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        process_videos([], tmp_path, fmt="webp", options=_color_options())
