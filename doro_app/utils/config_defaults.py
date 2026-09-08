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


# ═══════════════════════════════════════════════════════════
# Automation (Phase 1c) Defaults
# ═══════════════════════════════════════════════════════════

# Master opt-in for synthetic-click automation. `DORO_MOUSE=true` flips this
# on at process start. Anything else (unset, "0", "false") leaves it off.
DEFAULT_MOUSE_AUTOMATION_ENABLED = _env("DORO_MOUSE", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Master opt-in for accessibility-tree reading (Phase 1d). Independent of
# `mouse_enabled`: the user may want Doro to *see* the foreground window
# without being allowed to click, or vice versa. `DORO_A11Y=true` flips it on.
DEFAULT_A11Y_ENABLED = _env("DORO_A11Y", "false").strip().lower() in ("1", "true", "yes", "on")

# Secondary opt-in: when a11y is on, do we also forward the *content* of
# input/value fields (URL bar, search box, half-typed text) to the LLM?
# Defaults to off — Doro can still see "there's an input at (x, y) named
# '網址列'", just not what's typed there. The settings dialog exposes a
# checkbox so a user who knowingly wants the AI to act on field contents
# can opt in.
DEFAULT_A11Y_SHARE_INPUT_VALUES = False

# 網頁操作（第 3 層）總開關，預設關。可用環境變數 `DORO_WEB_OPERATE=true` 覆寫，
# 但主要靠 doro 設定裡的打勾開關（會記住）。
DEFAULT_WEB_OPERATION_ENABLED = _env("DORO_WEB_OPERATE", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


# ═══════════════════════════════════════════════════════════
# Web / Verify (search API) Defaults
# ═══════════════════════════════════════════════════════════

# Tavily search API key（查證用；與聊天 LLM 的 api_key 分開存）。可用環境變數覆寫。
DEFAULT_TAVILY_API_KEY = _env("DORO_TAVILY_API_KEY", "")
# 查證搜尋深度：basic（1 credit、較快、預設）或 advanced（2 credits、內容較長）。
DEFAULT_VERIFY_SEARCH_DEPTH = _env("DORO_VERIFY_SEARCH_DEPTH", "basic")
