"""GIF 轉 GIF:讀網路動圖、統一畫布大小、輸出透明 GIF。"""

from pathlib import Path

import pytest
from PIL import Image

from doro_app.core.gif_factory import (
    DoroSpec,
    MattingOptions,
    apply_doro_layout,
    body_bounds,
    extract_frames,
    fit_to_canvas,
    fit_to_doro,
    flip_frames,
    plan_doro_layout,
    process_videos,
    remove_background,
    save_animation,
)
from doro_app.core.gif_factory.__main__ import main
from doro_app.core.gif_factory.pipeline import doro_layout_for_frame, frame_layout_is_exact
from doro_app.core.gif_factory.preview import overlay_doro_reference


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


def _padded_frames(n=3, canvas=(400, 300), body=(60, 120), step=10):
    """大量透明留白中間一個會左右移動的角色(長方塊)。"""
    frames = []
    for i in range(n):
        img = Image.new("RGBA", canvas, (0, 0, 0, 0))
        left = 100 + i * step
        img.paste((0, 0, 255, 255), (left, 50, left + body[0], 50 + body[1]))
        frames.append(img)
    return frames


def test_body_bounds_is_union_across_frames():
    frames = _padded_frames(n=3, step=10)

    assert body_bounds(frames) == (100, 50, 180, 170)


def test_body_bounds_ignores_faint_matting_residue():
    frame = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    frame.putpixel((0, 0), (255, 255, 255, 10))
    frame.paste((0, 0, 0, 255), (20, 20, 30, 40))

    assert body_bounds([frame]) == (20, 20, 30, 40)
    assert body_bounds([Image.new("RGBA", (5, 5))]) is None


def test_fit_to_doro_trims_padding_and_stands_on_doro_foot_line():
    placed = fit_to_doro(_padded_frames(n=1), DoroSpec(body_height=150))

    assert placed[0].size == (200, 200)
    # 60×120 → 身高 150:寬 75,水平置中、腳底邊界 y=186(最後實心列 185)。
    assert placed[0].getchannel("A").getbbox() == (62, 36, 137, 186)
    assert placed[0].getpixel((100, 185))[3] == 255
    assert placed[0].getpixel((100, 186))[3] == 0


def test_default_body_height_matches_reference_stand_doro():
    stand = Image.open(Path(__file__).parents[2] / "doro_app/res/state/stand.gif").convert("RGBA")
    _, top, _, bottom = stand.getchannel("A").getbbox()

    assert (bottom - top, bottom) == (DoroSpec().body_height, DoroSpec().foot_y)


def _jump_frames():
    """原地站兩格,再跳起 120 像素一格;角色本體始終 60×120。"""
    return [
        _padded_frames(n=1, canvas=(400, 400))[0],
        _padded_frames(n=1, canvas=(400, 400))[0],
        _shifted(_padded_frames(n=1, canvas=(400, 400))[0], dy=-20),
    ]


def _solid_box(image):
    """alpha >= 128 的範圍;忽略 LANCZOS 縮放在邊緣留下的淡淡半透明。"""
    return image.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()


def _shifted(image, dx=0, dy=0):
    moved = Image.new("RGBA", image.size, (0, 0, 0, 0))
    moved.paste(image, (dx, dy))
    return moved


def test_jumping_does_not_shrink_the_character():
    placed = fit_to_doro(_jump_frames(), DoroSpec(body_height=150))
    boxes = [_solid_box(f) for f in placed]

    assert {b[3] - b[1] for b in boxes} == {150}  # 每格都是完整身高
    assert boxes[0][3] == 186  # 站著的腳踩在地面線
    assert boxes[2][3] < 186  # 跳起的那格保留離地高度


def test_horizontal_travel_keeps_size_and_reports_clipping():
    frames = [_padded_frames(n=1, canvas=(600, 300))[0]]
    frames.append(_shifted(frames[0], dx=150))

    layout = plan_doro_layout(frames, DoroSpec(body_height=150))
    placed = apply_doro_layout(frames, layout, 200)

    assert [_solid_box(f)[3] - _solid_box(f)[1] for f in placed] == [150, 150]
    assert layout.clipped_frames == 2  # 活動範圍 262 像素寬,兩端各超出 200 畫布一點


def test_travel_wider_than_canvas_can_push_frames_fully_out_but_is_reported():
    frames = [_padded_frames(n=1, canvas=(600, 300))[0]]
    frames.append(_shifted(frames[0], dx=300))

    layout = plan_doro_layout(frames, DoroSpec(body_height=150))

    # 刻意不縮小角色;代價是這種橫越整個畫面的素材會有格數整個被裁掉,所以必須回報。
    assert apply_doro_layout(frames, layout, 200)[0].getbbox() is None
    assert layout.clipped_frames == 2


def test_layout_without_overflow_reports_no_clipping():
    layout = plan_doro_layout(_padded_frames(n=3, step=10))

    assert layout.clipped_frames == 0


def test_size_uses_median_frame_not_odd_one_out():
    frames = _padded_frames(n=3, step=0)
    frames.append(_padded_frames(n=1, body=(60, 240), canvas=(400, 400))[0])

    layout = plan_doro_layout(frames, DoroSpec(body_height=150))

    assert layout.scale == pytest.approx(150 / 120)


def test_single_frame_uses_whole_animation_layout_when_not_matting():
    frames = _jump_frames()
    options = MattingOptions(mode="none")
    spec = DoroSpec(body_height=150)
    matted = remove_background(frames[2], options)

    single = apply_doro_layout([matted], doro_layout_for_frame(frames, matted, options, spec), 200)

    assert single[0].tobytes() == fit_to_doro(frames, spec)[2].tobytes()


def test_single_frame_layout_is_an_estimate_when_matting():
    frames = _jump_frames()
    options = MattingOptions(mode="color", color_key=(1, 2, 3), tolerance=0)
    matted = remove_background(frames[2], options)

    layout = doro_layout_for_frame(frames, matted, options, DoroSpec())

    assert not frame_layout_is_exact(options)
    assert layout == plan_doro_layout([matted], DoroSpec())


def test_fit_to_doro_uses_one_scale_for_whole_animation():
    placed = fit_to_doro(_padded_frames(n=3, step=10), DoroSpec(body_height=120))

    boxes = [f.getchannel("A").getbbox() for f in placed]
    # 整支共用裁切框,角色仍在畫面中移動、大小不變、腳都在 186。
    assert len({b[0] for b in boxes}) == 3
    assert {(b[2] - b[0], b[1], b[3]) for b in boxes} == {(60, 66, 186)}


def test_fit_to_doro_caps_wide_poses():
    lying = _padded_frames(n=1, body=(300, 60))

    box = fit_to_doro(lying, DoroSpec())[0].getchannel("A").getbbox()

    assert box[2] - box[0] == 190
    assert box[3] == 186


def test_fit_to_doro_keeps_empty_animation_empty():
    placed = fit_to_doro([Image.new("RGBA", (30, 30))] * 2)

    assert [f.size for f in placed] == [(200, 200)] * 2
    assert placed[0].getbbox() is None


@pytest.mark.parametrize(
    "kwargs",
    [{"body_height": 0}, {"body_height": 190}, {"foot_y": 201}, {"max_body_width": 0}],
)
def test_doro_spec_rejects_impossible_layouts(kwargs):
    with pytest.raises(ValueError):
        DoroSpec(**kwargs)


def test_differently_padded_gifs_end_up_with_the_same_body(tmp_path):
    tight = tmp_path / "tight.gif"
    loose = tmp_path / "loose.gif"
    save_animation(_padded_frames(canvas=(190, 180)), "gif", tight, fps=10)
    save_animation(_padded_frames(canvas=(600, 600)), "gif", loose, fps=10)

    outputs = process_videos(
        [tight, loose],
        tmp_path / "out",
        fmt="webp",
        options=MattingOptions(mode="none"),
        doro=DoroSpec(),
    )

    bodies = [extract_frames(p).frames[0].getchannel("A").getbbox() for p in outputs]
    assert bodies[0] == bodies[1]
    assert bodies[0][3] == 186


def test_cli_doro_mode(tmp_path):
    source = tmp_path / "in.gif"
    save_animation(_padded_frames(), "gif", source, fps=10)
    out = tmp_path / "out.webp"

    assert main([str(source), str(out), "--doro", "--body-height", "100", "--no-matting"]) == 0
    box = extract_frames(out).frames[0].getchannel("A").getbbox()
    assert (box[1], box[3]) == (86, 186)


def test_cli_doro_rejects_size(tmp_path):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "a.gif"), str(tmp_path / "b.gif"), "--doro", "--size", "100"])


def test_doro_reference_overlay_draws_ghost_behind_and_foot_line():
    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    image.putpixel((5, 5), (0, 255, 0, 255))
    reference = Image.new("RGBA", (40, 40), (255, 255, 255, 255))

    result = overlay_doro_reference(image, reference, foot_y=15)

    assert result.getpixel((5, 5)) == (0, 255, 0, 255)  # 素材在參考圖上面
    assert 0 < result.getpixel((10, 2))[3] < 255  # 參考圖半透明
    assert result.getpixel((0, 15)) == (230, 60, 60, 255)  # 腳底虛線


def test_doro_reference_scales_around_its_feet():
    reference = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    reference.paste((255, 255, 255, 255), (40, 20, 60, 80))  # 高 60、腳在 80

    result = overlay_doro_reference(
        Image.new("RGBA", (100, 100)), reference, foot_y=80, opacity=1.0, reference_scale=0.5
    )

    box = _solid_box(result.crop((0, 0, 100, 80)))
    assert box == (45, 50, 55, 80)  # 縮成一半高,腳仍在 80、仍然置中


def test_gif_palette_is_not_spent_on_hidden_transparent_colors(tmp_path):
    frame = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    colors = [(i, 255 - i, (i * 7) % 256, 255) for i in range(1, 256)]
    for index, color in enumerate(colors):
        frame.putpixel((index % 16, index // 16), color)
    # (15, 15) 保持透明,藏的顏色是黑色;不該擠掉 255 個可見色中的任何一個。
    out = save_animation([frame, frame.copy()], "gif", tmp_path / "p.gif", fps=10)

    result = extract_frames(out).frames[0]
    assert [result.getpixel((i % 16, i // 16)) for i in range(255)] == colors
    assert result.getpixel((15, 15))[3] == 0


@pytest.mark.parametrize("fmt", ["webp", "apng"])
def test_short_webp_and_apng_frames_keep_their_timing(tmp_path, fmt):
    # 60 fps 動圖每格約 16~17 毫秒,不能被當成 GIF 的「瀏覽器保底 100 毫秒」。
    path = save_animation(
        _moving_square_frames(n=3), fmt, tmp_path / f"fast.{fmt}", fps=60, durations=[16, 17, 17]
    )

    assert extract_frames(path).durations == [16, 17, 17]


def test_gif_keeps_20ms_frames_but_treats_10ms_as_browser_default(tmp_path):
    frames = [f.convert("RGB") for f in _moving_square_frames(n=2)]
    fast = tmp_path / "fast.gif"
    frames[0].save(fast, save_all=True, append_images=frames[1:], duration=[20, 10], loop=0)

    assert extract_frames(fast).durations == [20, 100]


def _marked_frame():
    """透明底,左上角一個紅點:翻轉後紅點的位置一看就知道。"""
    img = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    img.putpixel((1, 1), (255, 0, 0, 255))
    return img


def test_flip_frames_mirrors_each_direction():
    frame = _marked_frame()

    assert flip_frames([frame]) == [frame]  # 不翻就原樣
    assert flip_frames([frame], horizontal=True)[0].getpixel((18, 1))[3] == 255
    assert flip_frames([frame], vertical=True)[0].getpixel((1, 8))[3] == 255
    assert flip_frames([frame], horizontal=True, vertical=True)[0].getpixel((18, 8))[3] == 255


def test_process_video_flips_before_saving(tmp_path):
    source = save_animation(
        [_marked_frame(), _shifted(_marked_frame(), dx=1)], "gif", tmp_path / "in.gif", fps=10
    )

    out = process_videos(
        [source], tmp_path / "out", fmt="webp", options=MattingOptions(mode="none"), flip_h=True
    )[0]

    assert extract_frames(out).frames[0].getpixel((18, 1))[3] == 255


def test_cli_flip_flags(tmp_path):
    source = save_animation(
        [_marked_frame(), _shifted(_marked_frame(), dx=1)], "gif", tmp_path / "in.gif", fps=10
    )
    out = tmp_path / "out.webp"

    assert main([str(source), str(out), "--no-matting", "--flip-h", "--flip-v"]) == 0
    assert extract_frames(out).frames[0].getpixel((18, 8))[3] == 255
