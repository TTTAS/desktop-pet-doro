"""Prompt text storage utilities for Doro."""

from __future__ import annotations

from pathlib import Path

DEFAULT_PROMPT_TEXT = (
    "You are Doro, a cheerful desktop companion. Keep responses short and friendly."
)


def load_prompt_text(path: Path, *, default_prompt: str = DEFAULT_PROMPT_TEXT) -> str:
    """Load the persisted prompt text, falling back to a default."""
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


def write_prompt_text(path: Path, text: str) -> None:
    """Persist prompt text to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
