"""Central place for configurable default values."""

from __future__ import annotations

import os


def _env(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else fallback


DEFAULT_CHAT_SERVER_URL = _env("DORO_CHAT_SERVER_URL", "http://127.0.0.1:1234")
