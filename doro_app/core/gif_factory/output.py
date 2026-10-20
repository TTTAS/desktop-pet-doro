"""接縫 3 — 輸出。

用 Pillow 把一串影格存成動畫檔(WebP、APNG 或 GIF),沿用來源時間、保留透明。
GIF 只有一位元透明(全透明或不透明),半透明邊緣會以 50% 為界取捨。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

_SUPPORTED = {"webp", "apng", "gif"}

# GIF 調色盤中保留給透明的索引;其餘 255 色給畫面。
_GIF_TRANSPARENT_INDEX = 255

# alpha 低於這個值當成背景殘渣,不算進角色範圍(AI 去背常留下很淡的雜點)。
_BODY_ALPHA_THRESHOLD = 32

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class DoroSpec:
    """Doro 內建素材的版面規格(量自 doro_app/res 內建動畫)。

    內建動畫都是 200×200 畫布;站姿 stand.gif 的角色本體高 167 像素,
    腳底邊界在 y=186(也就是最後一列實心像素是 y=185,和 Pillow getbbox
    的右/下界不含該像素一致)。預設身高對齊 stand.gif,預覽疊的參考 Doro
    才會和成品同高;待機類約 146~149、坐姿等較矮的動作可以調低。
    """

    canvas: int = 200
    body_height: int = 167  # 角色本體高度(像素),對齊內建站姿
    foot_y: int = 186  # 腳底邊界的 y(從畫布頂端算,不含該列)
    max_body_width: int = 190  # 橫向姿勢的寬度上限,避免被放大到超出畫布

    def __post_init__(self) -> None:
        if not 0 < self.body_height <= self.foot_y <= self.canvas:
            raise ValueError(
                f"需要 0 < 身高({self.body_height}) <= 腳底({self.foot_y}) <= 畫布({self.canvas})"
            )
        if not 0 < self.max_body_width <= self.canvas:
            raise ValueError(f"寬度上限要在 1..{self.canvas},收到 {self.max_body_width}")


@dataclass(frozen=True)
class DoroLayout:
    """整支動畫共用的一組變換:裁切框、縮放比例與貼上位置。

    預覽、整支輸出與單格 PNG 都套用同一個 DoroLayout,三者的大小與位置才會一致。
    """

    crop: Box  # 原圖座標中要保留的範圍(所有影格角色範圍的聯集)
    scale: float
    origin: tuple[int, int]  # crop 縮放後左上角在畫布上的位置(可為負,超出部分被裁掉)
    canvas: int
    clipped_frames: int  # 有幾格的角色超出畫布、被裁切


def _frame_box(frame: Image.Image) -> Box | None:
    alpha = frame.convert("RGBA").getchannel("A")
    return alpha.point(lambda a: 255 if a >= _BODY_ALPHA_THRESHOLD else 0).getbbox()


def body_bounds(frames: list[Image.Image]) -> Box | None:
    """所有影格合起來的角色範圍(left, top, right, bottom);全透明回傳 None。

    右/下界和 Pillow getbbox 一樣不含該像素。這是動畫的「活動範圍」,
    用來裁切與檢查是否超出畫布,不拿來決定角色大小(見 plan_doro_layout)。
    """
    boxes = [box for box in map(_frame_box, frames) if box is not None]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def plan_doro_layout(frames: list[Image.Image], spec: DoroSpec | None = None) -> DoroLayout | None:
    """算出把角色擺成 Doro 規格的變換;全透明回傳 None。

    角色大小和動畫活動範圍分開處理:
    - 縮放:用「每格角色高度/寬度的中位數」對齊 spec 的身高與寬度上限,
      跳躍或位移不會把角色縮小。
    - 位置:所有影格中最低的腳(聯集下緣)對到 spec.foot_y,活動範圍水平置中;
      整支共用同一個變換,跳躍與位移原樣保留。
    - 活動範圍放不進畫布時不偷偷縮小角色,而是裁掉超出部分並回報格數。
    """
    spec = spec or DoroSpec()
    boxes = [_frame_box(f) for f in frames]
    present = [b for b in boxes if b is not None]
    if not present:
        return None

    height = statistics.median(b[3] - b[1] for b in present)
    width = statistics.median(b[2] - b[0] for b in present)
    scale = min(spec.body_height / height, spec.max_body_width / width)

    crop = body_bounds(frames)
    assert crop is not None  # present 非空時必有聯集
    crop_w = (crop[2] - crop[0]) * scale
    crop_h = (crop[3] - crop[1]) * scale
    origin = (round((spec.canvas - crop_w) / 2), round(spec.foot_y - crop_h))

    clipped = 0
    for box in present:
        left = origin[0] + (box[0] - crop[0]) * scale
        top = origin[1] + (box[1] - crop[1]) * scale
        right = origin[0] + (box[2] - crop[0]) * scale
        bottom = origin[1] + (box[3] - crop[1]) * scale
        if left < -0.5 or top < -0.5 or right > spec.canvas + 0.5 or bottom > spec.canvas + 0.5:
            clipped += 1
    return DoroLayout(
        crop=crop, scale=scale, origin=origin, canvas=spec.canvas, clipped_frames=clipped
    )


def apply_doro_layout(
    frames: list[Image.Image], layout: DoroLayout | None, canvas: int
) -> list[Image.Image]:
    """把同一個變換套到每一格;layout 為 None(全透明)時回傳空白畫布。"""
    empty = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    if layout is None:
        return [empty.copy() for _ in frames]

    crop = layout.crop
    size = (
        max(1, round((crop[2] - crop[0]) * layout.scale)),
        max(1, round((crop[3] - crop[1]) * layout.scale)),
    )
    placed = []
    for frame in frames:
        body = frame.convert("RGBA").crop(crop).resize(size, Image.LANCZOS)
        result = empty.copy()
        result.paste(body, layout.origin)  # 負座標或超出畫布的部分會被裁掉
        placed.append(result)
    return placed


def fit_to_doro(frames: list[Image.Image], spec: DoroSpec | None = None) -> list[Image.Image]:
    """plan_doro_layout + apply_doro_layout 的捷徑:整支動畫擺成 Doro 規格。"""
    spec = spec or DoroSpec()
    return apply_doro_layout(frames, plan_doro_layout(frames, spec), spec.canvas)


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
    rgb = np.array(rgba.convert("RGB"))
    visible = np.array(rgba.getchannel("A")) >= 128
    if visible.any():
        # 透明像素藏的 RGB(常是黑色)不該佔用調色盤,先填成畫面裡已有的顏色。
        rgb[~visible] = rgb[visible][0]
    paletted = Image.fromarray(rgb, "RGB").quantize(colors=_GIF_TRANSPARENT_INDEX)
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
