"""設定持久化:記住使用者上次選的輸出資料夾與格式。

存一個小 JSON 在使用者家目錄。這是純邏輯(不碰 GUI),方便測試。
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".gif_factory.json"

DEFAULTS: dict = {
    "output_dir": str(Path.home()),
    "fmt": "webp",
    "resize": True,  # 是否縮小輸出
    "output_size": 200,  # 縮小後的長邊像素
}


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    """讀設定;檔案不存在或壞掉時,回傳一份預設值(不會炸)。"""
    path = Path(path)
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return dict(DEFAULTS)

    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_config(config: dict, path: str | Path = CONFIG_PATH) -> Path:
    """把設定寫回 JSON,只保留認得的欄位。"""
    path = Path(path)
    to_save = {k: config[k] for k in DEFAULTS if k in config}
    path.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
