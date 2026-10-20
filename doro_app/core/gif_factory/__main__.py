"""腳本入口(命令列版,快速測試/批次用)。

用法:
  單支動畫:  python -m doro_app.core.gif_factory 影片.mp4 輸出.webp [--fmt webp|apng|gif] [--size 200]
  批量動畫:  python -m doro_app.core.gif_factory a.mp4 b.mp4 c.mp4 --out-dir 資料夾 [--fmt ...] [--size ...]
  挑一格存圖:python -m doro_app.core.gif_factory 影片.mp4 圖片.png --frame 25 [--size 200]
  GIF 統一大小:python -m doro_app.core.gif_factory a.gif b.gif --out-dir 資料夾 --fmt gif \
               --size 200 --canvas --no-matting
  對齊 Doro:  python -m doro_app.core.gif_factory a.gif b.gif --out-dir 資料夾 --doro [--body-height 150]

輸入可以是影片,也可以是 GIF / WebP / APNG 動圖。
去背預設用 AI 設定(isnet-anime);--no-matting 保留原圖透明、不去背。
--flip-h／--flip-v 先左右／上下翻轉(素材面向另一邊時)。
要調參數/滴管取色請用Doro 右鍵選單的素材工廠
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from doro_app.core.gif_factory.frames import extract_frames, flip_frames
from doro_app.core.gif_factory.matting import MattingOptions, remove_background
from doro_app.core.gif_factory.output import DoroLayout, DoroSpec, apply_doro_layout, save_image
from doro_app.core.gif_factory.pipeline import (
    doro_layout_for_frame,
    process_video,
    process_videos,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doro_app.core.gif_factory",
        description=(
            "把 ComfyUI 的 mp4 或網路上的 GIF 去背並輸出成 WebP / APNG / GIF 動畫檔,"
            "或挑一格存成 PNG。"
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="單支:<影片> <輸出路徑>。批量:多支影片,並用 --out-dir 指定輸出資料夾",
    )
    parser.add_argument(
        "--out-dir",
        help="批量輸出資料夾:給多支影片,每支各出一個 <檔名>.<fmt>",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="只挑第 N 格(從 1 起算)去背後存成 PNG 靜態圖,而非整支動畫",
    )
    parser.add_argument(
        "--fmt",
        choices=["webp", "apng", "gif"],
        default="webp",
        help="動畫輸出格式(預設 webp)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=None,
        help="輸出縮到長邊幾像素(例如 200);不給則維持原始尺寸",
    )
    parser.add_argument(
        "--canvas",
        action="store_true",
        help="搭配 --size:統一放進 size×size 透明畫布(可放大、底部置中),讓輸出大小一致",
    )
    parser.add_argument(
        "--doro",
        action="store_true",
        help="對齊 Doro 規格:裁掉留白、縮到 Doro 身高、腳踩在 200×200 畫布的 y=186",
    )
    parser.add_argument(
        "--body-height",
        type=int,
        default=DoroSpec.body_height,
        help=f"搭配 --doro:角色本體高度(預設 {DoroSpec.body_height},坐姿/趴姿可調低)",
    )
    parser.add_argument(
        "--flip-h",
        action="store_true",
        help="去背前先左右翻轉(角色面向另一邊時)",
    )
    parser.add_argument(
        "--flip-v",
        action="store_true",
        help="去背前先上下翻轉",
    )
    parser.add_argument(
        "--no-matting",
        action="store_true",
        help="不去背,保留原圖透明(例如只想把 GIF 統一大小或換格式)",
    )
    args = parser.parse_args(argv)
    if args.canvas and args.size is None:
        parser.error("--canvas 需要搭配 --size 指定畫布邊長")
    if args.doro and (args.size is not None or args.canvas):
        parser.error("--doro 已固定 200×200 畫布,不能再搭配 --size / --canvas")
    doro = None
    if args.doro:
        try:
            doro = DoroSpec(body_height=args.body_height)
        except ValueError as err:
            parser.error(str(err))
    options = MattingOptions(mode="none") if args.no_matting else None
    sizing = {
        "size": args.size,
        "canvas": args.canvas,
        "options": options,
        "doro": doro,
        "flip_h": args.flip_h,
        "flip_v": args.flip_v,
    }

    # 模式一:批量動畫(--out-dir 一給,所有 paths 都當輸入影片)。
    if args.out_dir:
        return _batch(args.paths, args.out_dir, args.fmt, **sizing)

    # 沒 --out-dir:最後一個 path 是輸出,其餘是輸入。單支才走得通。
    if len(args.paths) < 2:
        parser.error("需要 <影片> <輸出路徑>,或用 --out-dir 批量處理多支影片")
    *inputs, output = args.paths
    if len(inputs) > 1:
        parser.error("多支輸入影片請用 --out-dir 指定輸出資料夾(不是逐一給輸出路徑)")
    video = inputs[0]

    # 模式二:挑一格存成靜態 PNG。
    if args.frame is not None:
        return _save_single_frame(video, output, args.frame, **sizing)

    # 模式三:單支動畫。
    return _single(video, output, args.fmt, **sizing)


def _warn_clipped(name: str, layout: DoroLayout | None) -> None:
    if layout is not None and layout.clipped_frames:
        print(
            f"\n  注意:{name} 有 {layout.clipped_frames} 格動作超出畫布,超出部分已裁掉",
            file=sys.stderr,
        )


def _single(
    video: str,
    output: str,
    fmt: str,
    size: int | None,
    canvas: bool = False,
    options: MattingOptions | None = None,
    doro: DoroSpec | None = None,
    flip_h: bool = False,
    flip_v: bool = False,
) -> int:
    print("讀影片並去背中...(第一次跑會先下載 AI 模型,數百 MB,請稍候)")

    def show_progress(done: int, total: int) -> None:
        print(f"\r  去背進度 {done}/{total} 張影格", end="", flush=True)

    try:
        out = process_video(
            video,
            output,
            fmt=fmt,
            options=options,
            progress=show_progress,
            size=size,
            canvas=canvas,
            doro=doro,
            flip_h=flip_h,
            flip_v=flip_v,
            on_layout=lambda layout: _warn_clipped(Path(video).name, layout),
        )
    except (FileNotFoundError, ValueError) as err:
        print(f"\n錯誤:{err}", file=sys.stderr)
        return 1
    print(f"\n完成!輸出:{out}")
    return 0


def _batch(
    videos: list[str],
    out_dir: str,
    fmt: str,
    size: int | None,
    canvas: bool = False,
    options: MattingOptions | None = None,
    doro: DoroSpec | None = None,
    flip_h: bool = False,
    flip_v: bool = False,
) -> int:
    print(f"批量處理 {len(videos)} 支影片...(第一次跑會先下載 AI 模型,數百 MB)")

    def show_progress(fi: int, ftotal: int, done: int, total: int, name: str) -> None:
        print(f"\r  [{fi}/{ftotal}] {name} 去背 {done}/{total} 張   ", end="", flush=True)

    try:
        outs = process_videos(
            videos,
            out_dir,
            fmt=fmt,
            options=options,
            size=size,
            on_progress=show_progress,
            canvas=canvas,
            doro=doro,
            flip_h=flip_h,
            flip_v=flip_v,
            on_layout=_warn_clipped,
        )
    except (FileNotFoundError, ValueError) as err:
        print(f"\n錯誤:{err}", file=sys.stderr)
        return 1
    print(f"\n完成!共 {len(outs)} 個檔輸出到:{out_dir}")
    return 0


def _save_single_frame(
    video: str,
    output: str,
    frame_no: int,
    size: int | None,
    canvas: bool = False,
    options: MattingOptions | None = None,
    doro: DoroSpec | None = None,
    flip_h: bool = False,
    flip_v: bool = False,
) -> int:
    try:
        extracted = extract_frames(video)
    except (FileNotFoundError, ValueError) as err:
        print(f"錯誤:{err}", file=sys.stderr)
        return 1

    frames = flip_frames(extracted.frames, horizontal=flip_h, vertical=flip_v)
    total = len(frames)
    if not (1 <= frame_no <= total):
        print(f"錯誤:--frame 要在 1..{total} 之間,收到 {frame_no}", file=sys.stderr)
        return 1

    print(f"挑第 {frame_no}/{total} 格去背並存成 PNG...(第一次跑會先下載 AI 模型)")
    rgba = remove_background(frames[frame_no - 1], options)
    if doro is not None:
        layout = doro_layout_for_frame(frames, rgba, options, doro)
        rgba = apply_doro_layout([rgba], layout, doro.canvas)[0]
    out = save_image(rgba, output, size=None if doro else size, canvas=canvas)
    print(f"完成!輸出:{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
