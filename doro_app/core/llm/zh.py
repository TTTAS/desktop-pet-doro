"""Convert Doro's spoken lines to Taiwan Traditional Chinese."""

from __future__ import annotations

from functools import lru_cache

import opencc


@lru_cache(maxsize=1)
def _converter() -> opencc.OpenCC:
    # s2twp：簡體 → 台灣繁體，連用語一起換（点击 → 點選）。字典載入較慢，只建一次。
    return opencc.OpenCC("s2twp")


def to_traditional(text: str) -> str:
    """Convert a line Doro will say; quotes of Simplified pages are converted too."""
    if not text:
        return text
    return _converter().convert(text)
