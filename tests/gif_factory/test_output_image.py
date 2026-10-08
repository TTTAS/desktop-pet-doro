"""挑一格存成靜態圖片測試:save_image(單張 → 透明 PNG)。"""

from PIL import Image

from doro_app.core.gif_factory import save_image


def test_saved_image_exists(tmp_path):
    path = save_image(Image.new("RGBA", (32, 32), (255, 0, 0, 255)), tmp_path / "one.png")
    assert path.exists()
    assert path.stat().st_size > 0


def test_saved_image_is_png(tmp_path):
    path = save_image(Image.new("RGBA", (32, 32)), tmp_path / "one.png")
    with Image.open(path) as img:
        assert img.format == "PNG"


def test_saved_image_keeps_transparency(tmp_path):
    src = Image.new("RGBA", (32, 32), (255, 0, 0, 0))  # 全透明
    path = save_image(src, tmp_path / "one.png")
    with Image.open(path) as img:
        alpha = img.convert("RGBA").getchannel("A")
        assert alpha.getextrema()[0] == 0


def test_saved_image_with_size_shrinks(tmp_path):
    path = save_image(Image.new("RGBA", (1024, 1024)), tmp_path / "one.png", size=200)
    with Image.open(path) as img:
        assert img.size == (200, 200)


def test_saved_image_without_size_keeps_original(tmp_path):
    path = save_image(Image.new("RGBA", (320, 240)), tmp_path / "one.png")
    with Image.open(path) as img:
        assert img.size == (320, 240)


def test_saved_image_converts_non_rgba(tmp_path):
    # 來源是 RGB(拆出來的影格就是 RGB),存出來仍要是可帶透明的 PNG。
    path = save_image(Image.new("RGB", (16, 16), (10, 20, 30)), tmp_path / "one.png")
    with Image.open(path) as img:
        assert img.convert("RGBA").getpixel((0, 0)) == (10, 20, 30, 255)
