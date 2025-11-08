from __future__ import annotations

from pathlib import Path

DEFAULT_PROMPT_TEXT = "You are Doro, a cheerful desktop companion. Keep responses short and friendly."


def safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_prompt_text(path: Path, *, default_prompt: str = DEFAULT_PROMPT_TEXT) -> str:
    try:
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
            stripped = raw.strip()
            if stripped:
                return stripped
    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_prompt, encoding="utf-8")
    except OSError:
        pass
    return default_prompt


def write_prompt_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


__all__ = [
    "DEFAULT_PROMPT_TEXT",
    "load_prompt_text",
    "safe_float",
    "safe_int",
    "write_prompt_text",
]
