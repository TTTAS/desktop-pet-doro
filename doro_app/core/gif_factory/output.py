"""接縫 3 — 輸出。

用 Pillow 把一串影格存成動畫檔(WebP、APNG 或 GIF),沿用來源時間、保留透明。
GIF 只有一位元透明(全透明或不透明),半透明邊緣會以 50% 為界取捨。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_SUPPORTED = {"webp", "apng", "gif"}

# GIF 調色盤中保留給透明的索引;其餘 255 色給畫面。
_GIF_TRANSPARENT_INDEX = 255

# alpha 低於這個值當成背景殘渣,不算進角色範圍(AI 去背常留下很淡的雜點)。
_BODY_ALPHA_THRESHOLD = 32


@dataclass(frozen=True)
class DoroSpec:
    """Doro 內建素材的版面規格(量自 doro_app/res 內建動畫)。

    內建動畫都是 200×200 畫布,角色本體高約 146~173 像素、腳踩在 y≈186。
    照這個規格擺放,外來素材在桌面上就會跟 Doro 一樣大、站在同一條線上。
    """

    canvas: int = 200
    body_height: int = 150  # 角色本體高度(像素),坐姿/趴姿可以調低
    foot_y: int = 186  # 腳底所在的 y(從畫布頂端算)
    max_body_width: int = 190  # 橫向姿勢的寬度上限,避免被放大到超出畫布

    def __post_init__(self) -> None:
        if not 0 < self.body_height <= self.foot_y <= self.canvas:
            raise ValueError(
                f"需要 0 < 身高({self.body_height}) <= 腳底({self.foot_y}) <= 畫布({self.canvas})"
            )
        if not 0 < self.max_body_width <= self.canvas:
            raise ValueError(f"寬度上限要在 1..{self.canvas},收到 {self.max_body_width}")


def body_bounds(frames: list[Image.Image]) -> tuple[int, int, int, int] | None:
    """所有影格合起來的角色範圍(left, top, right, bottom);全透明回傳 None。

    用聯集而不是逐格各算,整支動畫才會用同一個裁切與縮放,不會抖動。
    """
    bounds = None
    for frame in frames:
        alpha = frame.convert("RGBA").getchannel("A")
        box = alpha.point(lambda a: 255 if a >= _BODY_ALPHA_THRESHOLD else 0).getbbox()
        if box is None:
            continue
        if bounds is None:
            bounds = box
        else:
            bounds = (
                min(bounds[0], box[0]),
                min(bounds[1], box[1]),
                max(bounds[2], box[2]),
                max(bounds[3], box[3]),
            )
    return bounds


def fit_to_doro(
    frames: list[Image.Image],
    spec: DoroSpec | None = None,
    bounds: tuple[int, int, int, int] | None = None,
) -> list[Image.Image]:
    """裁掉透明留白、縮放到 Doro 身高,再把腳對到 Doro 的腳底線。

    整支動畫共用一個裁切框與縮放比例(見 body_bounds);縮放可放大也可縮小,
    但寬度不超過 max_body_width。角色水平置中,底緣對齊 spec.foot_y。
    bounds 可由呼叫端給定(例如預覽單格時沿用整支動畫的範圍)。
    """
    spec = spec or DoroSpec()
    rgba_frames = [f.convert("RGBA") for f in frames]
    empty = Image.new("RGBA", (spec.canvas, spec.canvas), (0, 0, 0, 0))
    if bounds is None:
        bounds = body_bounds(rgba_frames)
    if bounds is None:
        return [empty.copy() for _ in rgba_frames]

    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    scale = min(spec.body_height / height, spec.max_body_width / width)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    origin = ((spec.canvas - new_size[0]) // 2, spec.foot_y - new_size[1])

    placed = []
    for frame in rgba_frames:
        body = frame.crop(bounds).resize(new_size, Image.LANCZOS)
        canvas = empty.copy()
        canvas.paste(body, origin)
        placed.append(canvas)
    return placed


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


def _layout_frames(
    frames: list[Image.Image], size: int | None, canvas: bool, doro: DoroSpec | None
) -> list[Image.Image]:
    if doro is not None:
        return fit_to_doro(frames, doro)
    return [_apply_size(f.convert("RGBA"), size, canvas) for f in frames]


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
    doro: DoroSpec | None = None,
) -> Path:
    """把單張影格存成透明 PNG(挑一格當靜態圖用),回傳實際寫出的路徑。

    保留透明(RGBA)。size 若給定(長邊像素),存檔前先等比縮小(只縮不放),
    和動畫輸出一樣「在大圖去背後才縮」,邊緣才乾淨。canvas=True 時改成
    放進 size×size 的透明畫布(可放大),見 fit_to_canvas。doro 若給定,
    改用 Doro 規格擺放(見 fit_to_doro),忽略 size/canvas。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rgba = _layout_frames([image], size, canvas, doro)[0]
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
    doro: DoroSpec | None = None,
) -> Path:
    """把影格存成動畫檔,回傳實際寫出的路徑。

    fmt 接受 "webp"、"apng" 或 "gif";都保留透明並沿用來源 FPS。
    durations 若給定(每格毫秒,長度同 frames),改用逐格時間,保住 GIF 原本的節奏。
    size 若給定(長邊像素),會在存檔前把每張影格等比縮到該尺寸(只縮不放);
    canvas=True 時改成統一放進 size×size 透明畫布(可放大),見 fit_to_canvas。
    doro 若給定,改用 Doro 規格擺放(見 fit_to_doro),忽略 size/canvas。
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

    rgba_frames = _layout_frames(frames, size, canvas, doro)
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
