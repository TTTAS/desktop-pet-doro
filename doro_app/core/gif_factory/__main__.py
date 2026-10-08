"""腳本入口(命令列版,快速測試/批次用)。

用法:
  單支動畫:  python -m doro_app.core.gif_factory 影片.mp4 輸出.webp [--fmt webp|apng] [--size 200]
  批量動畫:  python -m doro_app.core.gif_factory a.mp4 b.mp4 c.mp4 --out-dir 資料夾 [--fmt ...] [--size ...]
  挑一格存圖:python -m doro_app.core.gif_factory 影片.mp4 圖片.png --frame 25 [--size 200]

去背一律用 AI 預設設定(isnet-anime)。要調參數/滴管取色請用Doro 右鍵選單的素材工廠
"""

from __future__ import annotations

import argparse
import sys

from doro_app.core.gif_factory.frames import extract_frames
from doro_app.core.gif_factory.matting import remove_background
from doro_app.core.gif_factory.output import save_image
from doro_app.core.gif_factory.pipeline import process_video, process_videos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doro_app.core.gif_factory",
        description="把 ComfyUI 的 mp4 去背並輸出成 WebP / APNG 動畫檔,或挑一格存成 PNG。",
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
        choices=["webp", "apng"],
        default="webp",
        help="動畫輸出格式(預設 webp)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=None,
        help="輸出縮到長邊幾像素(例如 200);不給則維持原始尺寸",
    )
    args = parser.parse_args(argv)

    # 模式一:批量動畫(--out-dir 一給,所有 paths 都當輸入影片)。
    if args.out_dir:
        return _batch(args.paths, args.out_dir, args.fmt, args.size)

    # 沒 --out-dir:最後一個 path 是輸出,其餘是輸入。單支才走得通。
    if len(args.paths) < 2:
        parser.error("需要 <影片> <輸出路徑>,或用 --out-dir 批量處理多支影片")
    *inputs, output = args.paths
    if len(inputs) > 1:
        parser.error("多支輸入影片請用 --out-dir 指定輸出資料夾(不是逐一給輸出路徑)")
    video = inputs[0]

    # 模式二:挑一格存成靜態 PNG。
    if args.frame is not None:
        return _save_single_frame(video, output, args.frame, args.size)

    # 模式三:單支動畫。
    return _single(video, output, args.fmt, args.size)


def _single(video: str, output: str, fmt: str, size: int | None) -> int:
    print("讀影片並去背中...(第一次跑會先下載 AI 模型,數百 MB,請稍候)")

    def show_progress(done: int, total: int) -> None:
        print(f"\r  去背進度 {done}/{total} 張影格", end="", flush=True)

    try:
        out = process_video(video, output, fmt=fmt, progress=show_progress, size=size)
    except (FileNotFoundError, ValueError) as err:
        print(f"\n錯誤:{err}", file=sys.stderr)
        return 1
    print(f"\n完成!輸出:{out}")
    return 0


def _batch(videos: list[str], out_dir: str, fmt: str, size: int | None) -> int:
    print(f"批量處理 {len(videos)} 支影片...(第一次跑會先下載 AI 模型,數百 MB)")

    def show_progress(fi: int, ftotal: int, done: int, total: int, name: str) -> None:
        print(f"\r  [{fi}/{ftotal}] {name} 去背 {done}/{total} 張   ", end="", flush=True)

    try:
        outs = process_videos(videos, out_dir, fmt=fmt, size=size, on_progress=show_progress)
    except (FileNotFoundError, ValueError) as err:
        print(f"\n錯誤:{err}", file=sys.stderr)
        return 1
    print(f"\n完成!共 {len(outs)} 個檔輸出到:{out_dir}")
    return 0


def _save_single_frame(video: str, output: str, frame_no: int, size: int | None) -> int:
    try:
        extracted = extract_frames(video)
    except (FileNotFoundError, ValueError) as err:
        print(f"錯誤:{err}", file=sys.stderr)
        return 1

    total = len(extracted.frames)
    if not (1 <= frame_no <= total):
        print(f"錯誤:--frame 要在 1..{total} 之間,收到 {frame_no}", file=sys.stderr)
        return 1

    print(f"挑第 {frame_no}/{total} 格去背並存成 PNG...(第一次跑會先下載 AI 模型)")
    rgba = remove_background(extracted.frames[frame_no - 1])
    out = save_image(rgba, output, size=size)
    print(f"完成!輸出:{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
