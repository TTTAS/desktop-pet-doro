"""接縫 3 — 輸出。

用 Pillow 把一串影格存成動畫檔(WebP、APNG 或 GIF),沿用來源時間、保留透明。
GIF 只有一位元透明(全透明或不透明),半透明邊緣會以 50% 為界取捨。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_SUPPORTED = {"webp", "apng", "gif"}

# GIF 調色盤中保留給透明的索引;其餘 255 色給畫面。
_GIF_TRANSPARENT_INDEX = 255


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


def fit_to_canvas(image: Image.Image, side: int) -> Image.Image:
    """把圖等比縮放(可放大)到長邊 = side,再放進 side×side 的透明畫布。

    水平置中、貼齊底部,讓角色的腳落在同一條線上。網路上抓的 GIF 大小不一,
    全部經過這一步就會變成同樣尺寸,在桌面上看起來一樣大。
    """
    if side <= 0:
        raise ValueError(f"輸出尺寸必須是正整數,收到 {side}")

    image = image.convert("RGBA")
    width, height = image.size
    scale = min(side / width, side / height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    if new_size != image.size:
        image = image.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - new_size[0]) // 2, side - new_size[1]))
    return canvas


def _apply_size(image: Image.Image, size: int | None, canvas: bool) -> Image.Image:
    if size is None:
        return image
    return fit_to_canvas(image, size) if canvas else resize_to_fit(image, size)


def _to_gif_frame(rgba: Image.Image) -> Image.Image:
    """RGBA → 調色盤圖:255 色畫面 + 一個透明索引(alpha < 128 視為透明)。"""
    paletted = rgba.convert("RGB").quantize(colors=_GIF_TRANSPARENT_INDEX)
    palette = (paletted.getpalette() or [])[: _GIF_TRANSPARENT_INDEX * 3]
    palette += [0] * (256 * 3 - len(palette))
    paletted.putpalette(palette)
    transparent = rgba.getchannel("A").point(lambda a: 255 if a < 128 else 0)
    paletted.paste(_GIF_TRANSPARENT_INDEX, mask=transparent)
    return paletted


def save_image(
    image: Image.Image,
    path: str | Path,
    size: int | None = None,
    canvas: bool = False,
) -> Path:
    """把單張影格存成透明 PNG(挑一格當靜態圖用),回傳實際寫出的路徑。

    保留透明(RGBA)。size 若給定(長邊像素),存檔前先等比縮小(只縮不放),
    和動畫輸出一樣「在大圖去背後才縮」,邊緣才乾淨。canvas=True 時改成
    放進 size×size 的透明畫布(可放大),見 fit_to_canvas。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rgba = image.convert("RGBA")
    rgba = _apply_size(rgba, size, canvas)
    rgba.save(path, format="PNG")
    return path


def save_animation(
    frames: list[Image.Image],
    fmt: str,
    path: str | Path,
    fps: float,
    size: int | None = None,
    durations: list[int] | None = None,
    canvas: bool = False,
) -> Path:
    """把影格存成動畫檔,回傳實際寫出的路徑。

    fmt 接受 "webp"、"apng" 或 "gif";都保留透明並沿用來源 FPS。
    durations 若給定(每格毫秒,長度同 frames),改用逐格時間,保住 GIF 原本的節奏。
    size 若給定(長邊像素),會在存檔前把每張影格等比縮到該尺寸(只縮不放);
    canvas=True 時改成統一放進 size×size 透明畫布(可放大),見 fit_to_canvas。
    """
    fmt = fmt.lower()
    if fmt not in _SUPPORTED:
        raise ValueError(f"不支援的格式:{fmt!r}(只能是 'webp'、'apng' 或 'gif')")
    if not frames:
        raise ValueError("沒有任何影格可以輸出")
    if fps <= 0:
        raise ValueError(f"FPS 必須是正數,收到 {fps}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if durations is not None and len(durations) != len(frames):
        raise ValueError(f"durations 數量({len(durations)})要和影格數({len(frames)})相同")

    rgba_frames = [_apply_size(f.convert("RGBA"), size, canvas) for f in frames]
    # Pillow 的動畫編碼器要的是整數毫秒,四捨五入避免被無聲截斷或報錯。
    if durations is not None:
        duration_ms: int | list[int] = [max(1, int(ms)) for ms in durations]
    else:
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
    elif fmt == "gif":
        gif_frames = [_to_gif_frame(f) for f in rgba_frames]
        gif_frames[0].save(
            path,
            format="GIF",
            save_all=True,
            append_images=gif_frames[1:],
            duration=duration_ms,
            loop=0,
            transparency=_GIF_TRANSPARENT_INDEX,
            disposal=2,  # 每格播完清回透明,避免上一格殘影疊在一起
            optimize=False,  # 不讓 Pillow 重排調色盤,透明索引才穩定
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
