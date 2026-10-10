"""接縫 3 — 輸出。

用 Pillow 把一串影格存成動畫檔(WebP 或 APNG),沿用來源 FPS、保留透明。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_SUPPORTED = {"webp", "apng"}


def resize_to_fit(image: Image.Image, max_side: int) -> Image.Image:
    """把圖等比縮到「長邊 = max_side」,用高品質 LANCZOS,保留透明。

    只縮小、不放大(來源比目標小時原樣回傳,避免放大變糊)。因為在原始大圖
    做完去背才縮小,邊緣會被平滑地縮下來,成品比先縮再處理清楚很多。
    """
    if max_side <= 0:
        raise ValueError(f"輸出尺寸必須是正整數,收到 {max_side}")

    image = image.convert("RGBA")
    width, height = image.size
    scale = min(max_side / width, max_side / height)
    if scale >= 1.0:
        return image

    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def save_image(
    image: Image.Image,
    path: str | Path,
    size: int | None = None,
) -> Path:
    """把單張影格存成透明 PNG(挑一格當靜態圖用),回傳實際寫出的路徑。

    保留透明(RGBA)。size 若給定(長邊像素),存檔前先等比縮小(只縮不放),
    和動畫輸出一樣「在大圖去背後才縮」,邊緣才乾淨。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rgba = image.convert("RGBA")
    if size is not None:
        rgba = resize_to_fit(rgba, size)
    rgba.save(path, format="PNG")
    return path


def save_animation(
    frames: list[Image.Image],
    fmt: str,
    path: str | Path,
    fps: float,
    size: int | None = None,
) -> Path:
    """把影格存成動畫檔,回傳實際寫出的路徑。

    fmt 只接受 "webp" 或 "apng";兩者都保留透明(RGBA)並沿用來源 FPS。
    size 若給定(長邊像素),會在存檔前把每張影格等比縮到該尺寸(只縮不放)。
    """
    fmt = fmt.lower()
    if fmt not in _SUPPORTED:
        raise ValueError(f"不支援的格式:{fmt!r}(只能是 'webp' 或 'apng')")
    if not frames:
        raise ValueError("沒有任何影格可以輸出")
    if fps <= 0:
        raise ValueError(f"FPS 必須是正數,收到 {fps}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rgba_frames = [f.convert("RGBA") for f in frames]
    if size is not None:
        rgba_frames = [resize_to_fit(f, size) for f in rgba_frames]
    # Pillow 的動畫編碼器要的是整數毫秒,四捨五入避免被無聲截斷或報錯。
    duration_ms = max(1, round(1000.0 / fps))  # 每張影格顯示幾毫秒

    first, rest = rgba_frames[0], rgba_frames[1:]
    if fmt == "webp":
        first.save(
            path,
            format="WEBP",
            save_all=True,
            append_images=rest,
            duration=duration_ms,
            loop=0,
            lossless=True,
        )
    else:  # apng
        first.save(
            path,
            format="PNG",
            save_all=True,
            append_images=rest,
            duration=duration_ms,
            loop=0,
        )

    return path
