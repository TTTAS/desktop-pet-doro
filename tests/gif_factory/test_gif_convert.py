"""GIF 轉 GIF:讀網路動圖、統一畫布大小、輸出透明 GIF。"""

import pytest
from PIL import Image

from doro_app.core.gif_factory import (
    MattingOptions,
    extract_frames,
    fit_to_canvas,
    process_videos,
    remove_background,
    save_animation,
)
from doro_app.core.gif_factory.__main__ import main


def _moving_square_frames(size=(40, 30), n=4):
    """透明底上一個逐格往右移的紅方塊;每格不同,不會被編碼器合併。"""
    frames = []
    for i in range(n):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        img.paste((255, 0, 0, 255), (i * 6, 5, i * 6 + 6, 11))
        frames.append(img)
    return frames


def _write_gif(path, size=(40, 30), durations=(50, 100, 150, 200)):
    frames = _moving_square_frames(size, len(durations))
    return save_animation(frames, "gif", path, fps=10, durations=list(durations))


def test_extract_gif_keeps_transparency_and_frame_durations(tmp_path):
    gif = _write_gif(tmp_path / "in.gif")

    result = extract_frames(gif)

    assert len(result.frames) == 4
    assert result.durations == [50, 100, 150, 200]
    assert result.fps == pytest.approx(8.0)
    first = result.frames[0]
    assert first.mode == "RGBA"
    assert first.getpixel((39, 29))[3] == 0
    assert first.getpixel((2, 7)) == (255, 0, 0, 255)


def test_gif_output_clears_previous_frame(tmp_path):
    result = extract_frames(_write_gif(tmp_path / "in.gif"))

    # disposal=2:上一格的方塊不能殘留在下一格。
    assert [f.getchannel("A").getbbox() for f in result.frames] == [
        (0, 5, 6, 11),
        (6, 5, 12, 11),
        (12, 5, 18, 11),
        (18, 5, 24, 11),
    ]


def test_zero_duration_gif_frames_play_at_browser_speed(tmp_path):
    gif = tmp_path / "fast.gif"
    frames = [f.convert("RGB") for f in _moving_square_frames(n=2)]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=0, loop=0)

    assert extract_frames(gif).durations == [100, 100]


def test_broken_gif_raises_value_error(tmp_path):
    bad = tmp_path / "bad.gif"
    bad.write_bytes(b"not a gif")

    with pytest.raises(ValueError):
        extract_frames(bad)


def test_fit_to_canvas_upscales_small_image_to_bottom_center():
    small = Image.new("RGBA", (20, 10), (0, 255, 0, 255))

    result = fit_to_canvas(small, 100)

    assert result.size == (100, 100)
    # 20×10 放大 5 倍 = 100×50,貼齊底部。
    assert result.getchannel("A").getbbox() == (0, 50, 100, 100)


def test_fit_to_canvas_shrinks_tall_image_and_centers_horizontally():
    tall = Image.new("RGBA", (100, 400), (0, 255, 0, 255))

    result = fit_to_canvas(tall, 200)

    assert result.size == (200, 200)
    assert result.getchannel("A").getbbox() == (75, 0, 125, 200)


def test_fit_to_canvas_rejects_non_positive_size():
    with pytest.raises(ValueError):
        fit_to_canvas(Image.new("RGBA", (4, 4)), 0)


def test_durations_must_match_frames(tmp_path):
    with pytest.raises(ValueError, match="durations"):
        save_animation(_moving_square_frames(n=3), "gif", tmp_path / "x.gif", 10, durations=[10])


def test_no_matting_keeps_original_alpha():
    image = _moving_square_frames(n=1)[0]

    result = remove_background(image, MattingOptions(mode="none"))

    assert result.tobytes() == image.tobytes()


@pytest.mark.parametrize("fmt", ["gif", "webp", "apng"])
def test_different_sized_gifs_come_out_the_same_size(tmp_path, fmt):
    small = _write_gif(tmp_path / "small.gif", size=(40, 30))
    large = _write_gif(tmp_path / "large.gif", size=(300, 120))

    outputs = process_videos(
        [small, large],
        tmp_path / "out",
        fmt=fmt,
        options=MattingOptions(mode="none"),
        size=128,
        canvas=True,
    )

    for path in outputs:
        with Image.open(path) as image:
            assert image.size == (128, 128)
        assert extract_frames(path).durations == [50, 100, 150, 200]


def test_cli_converts_gif_to_uniform_gif(tmp_path, capsys):
    source = _write_gif(tmp_path / "in.gif", size=(60, 20))
    out = tmp_path / "out.gif"

    code = main([str(source), str(out), "--fmt", "gif", "--size", "90", "--canvas", "--no-matting"])

    assert code == 0
    with Image.open(out) as image:
        assert image.format == "GIF"
        assert image.size == (90, 90)
        assert image.n_frames == 4


def test_cli_canvas_requires_size(tmp_path):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "in.gif"), str(tmp_path / "out.gif"), "--canvas"])
