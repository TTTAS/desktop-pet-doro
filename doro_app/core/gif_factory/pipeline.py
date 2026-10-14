"""端到端管線:把三個接縫接起來。mp4 / GIF → 去背 → 動畫檔。

視窗層只呼叫這裡(或個別接縫),不自己放處理邏輯。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PIL import Image

from doro_app.core.gif_factory.frames import extract_frames
from doro_app.core.gif_factory.matting import MattingOptions, remove_background
from doro_app.core.gif_factory.output import (
    DoroLayout,
    DoroSpec,
    apply_doro_layout,
    plan_doro_layout,
    save_animation,
)


class ProcessingCancelled(Exception):
    """A media job was cancelled between frames."""


def check_cancelled(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProcessingCancelled("已取消處理")


def available_output_path(path: str | Path) -> Path:
    """Keep previous exports, including inputs with the same filename."""
    path = Path(path)
    candidate = path
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        index += 1
    return candidate


def frame_layout_is_exact(options: MattingOptions | None) -> bool:
    """不去背且不內縮時,原圖透明就是成品透明,單格也能用整支動畫算出精確變換。"""
    return options is not None and options.mode == "none" and options.erode == 0


def doro_layout_for_frame(
    source_frames: list[Image.Image],
    matted: Image.Image,
    options: MattingOptions | None,
    spec: DoroSpec,
) -> DoroLayout | None:
    """單格(預覽 / PNG)要用的 Doro 變換,讓它和整支輸出盡量一致。

    不去背(且不內縮)時,原圖透明就是成品透明,用整支動畫計算,結果和整支輸出
    完全相同;去背模式要整支去背才知道範圍,只能以這一格估算。
    """
    exact = frame_layout_is_exact(options)
    return plan_doro_layout(source_frames if exact else [matted], spec)


def process_video(
    video_path: str | Path,
    output_path: str | Path,
    fmt: str = "webp",
    options: MattingOptions | None = None,
    progress: Callable[[int, int], None] | None = None,
    size: int | None = None,
    cancel: Event | None = None,
    canvas: bool = False,
    doro: DoroSpec | None = None,
    on_layout: Callable[[DoroLayout | None], None] | None = None,
) -> Path:
    """讀影片或動圖 → 逐張去背 → (可選)縮到指定尺寸 → 存成動畫檔。

    progress(done, total) 會在每張影格處理完後被呼叫,供視窗顯示進度。
    size 若給定(長邊像素),縮小發生在去背之後、存檔之前,以保住邊緣品質。
    canvas=True 時改成統一放進 size×size 透明畫布(可放大),讓大小不一的
    來源 GIF 輸出成同樣尺寸。doro 若給定,改成裁掉留白、對齊 Doro 的身高與
    腳底線(見 plan_doro_layout),並以 on_layout(layout) 回報這支用的變換
    (例如 layout.clipped_frames > 0 代表有影格超出畫布被裁切)。
    動圖來源會沿用每格原本的顯示時間。
    """
    check_cancelled(cancel)
    extracted = extract_frames(video_path, cancel=cancel)
    total = len(extracted.frames)

    processed = []
    for index, frame in enumerate(extracted.frames, start=1):
        check_cancelled(cancel)
        processed.append(remove_background(frame, options))
        if progress is not None:
            progress(index, total)

    check_cancelled(cancel)
    if doro is not None:
        layout = plan_doro_layout(processed, doro)
        if on_layout is not None:
            on_layout(layout)
        processed = apply_doro_layout(processed, layout, doro.canvas)
        size, canvas = None, False
    return save_animation(
        processed,
        fmt,
        output_path,
        extracted.fps,
        size=size,
        durations=extracted.durations,
        canvas=canvas,
    )


def process_videos(
    video_paths: list[str | Path],
    output_dir: str | Path,
    fmt: str = "webp",
    options: MattingOptions | None = None,
    size: int | None = None,
    on_progress: Callable[[int, int, int, int, str], None] | None = None,
    cancel: Event | None = None,
    canvas: bool = False,
    doro: DoroSpec | None = None,
    on_layout: Callable[[str, DoroLayout | None], None] | None = None,
) -> list[Path]:
    """批量處理多支影片:每支各自去背、輸出成 <檔名>.<fmt> 到 output_dir。

    同一組設定套用到所有影片,回傳所有輸出檔的路徑。逐支處理(每支自己拆影格),
    不會把所有影片的影格同時塞進記憶體。

    on_progress(file_index, file_total, frame_done, frame_total, name) 會在
    每支影片的每張影格處理完後被呼叫,供視窗顯示「第幾支 / 這支第幾張」的進度。
    on_layout(name, layout) 在對齊 Doro 規格時回報每支用的變換。
    """
    paths = [Path(p) for p in video_paths]
    if not paths:
        raise ValueError("沒有選到任何影片")

    output_dir = Path(output_dir)
    total_files = len(paths)
    results: list[Path] = []

    for file_index, video in enumerate(paths, start=1):
        check_cancelled(cancel)
        out_path = available_output_path(output_dir / f"{video.stem}.{fmt}")

        def frame_progress(done: int, total: int, _i=file_index, _n=video.name) -> None:
            if on_progress is not None:
                on_progress(_i, total_files, done, total, _n)

        def layout_report(layout: DoroLayout | None, _n=video.name) -> None:
            if on_layout is not None:
                on_layout(_n, layout)

        results.append(
            process_video(
                video,
                out_path,
                fmt=fmt,
                options=options,
                progress=frame_progress,
                size=size,
                cancel=cancel,
                canvas=canvas,
                doro=doro,
                on_layout=layout_report,
            )
        )

    return results
