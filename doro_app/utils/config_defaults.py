"""Central place for configurable default values."""

from __future__ import annotations

import os


def _env(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else fallback


# ═══════════════════════════════════════════════════════════
# Chat/LLM Configuration Defaults
# ═══════════════════════════════════════════════════════════

DEFAULT_CHAT_SERVER_URL = _env("DORO_CHAT_SERVER_URL", "http://127.0.0.1:1234")
DEFAULT_CHAT_MODEL = "lmstudio"  # Default LLM model identifier
DEFAULT_CHAT_ENDPOINT_PATH = "/v1/chat/completions"  # OpenAI-compatible API path
DEFAULT_CHAT_API_KEY = _env("DORO_CHAT_API_KEY", "")
DEFAULT_CHAT_MAX_RETRIES = 2  # Number of retries for failed requests
DEFAULT_CHAT_STOP_TOKENS = ["\n人：", "\n人:", "\n你：", "\n你:", "\nUser:", "\nHuman:"]
DEFAULT_CHAT_MAX_STOP_TOKENS = 0  # 0 = no limit
