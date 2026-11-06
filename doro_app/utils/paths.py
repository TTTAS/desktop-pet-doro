"""Common filesystem locations used by the Doro application."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
RESOURCES_DIR = PROJECT_ROOT / "res"
DRAG_DIR = RESOURCES_DIR / "drag"
ACTION_DIR = RESOURCES_DIR / "ACTION"
ACTION_MOVE_DIR = ACTION_DIR / "MOVE"
ACTION_TRANSITION_DIR = ACTION_DIR / "TRANSITION"
STATE_DIR = RESOURCES_DIR / "state"
MOVE_DIR = ACTION_MOVE_DIR
CORE_DIR = PROJECT_ROOT / "core"
CHAT_DIR = CORE_DIR / "chat"
PROMPT_PATH = CHAT_DIR / "dia_prompt.txt"
MOVEMENT_INSTRUCTION_PATH = CHAT_DIR / "movement_instruction.txt"
NETWORK_FAIL_MESSAGES_PATH = CHAT_DIR / "network_fail_doro.txt"
CLICK_ACTIONS_PATH = RESOURCES_DIR / "click.txt"
ACTIONS_JSON_PATH = RESOURCES_DIR / "state" / "actions.json"
COMPANION_PROMPTS_PATH = RESOURCES_DIR / "companion.txt"


def chat_log_path() -> Path:
    """本機對話紀錄（LoRA 訓練資料來源）。固定位置，匯出腳本才找得到；
    ``DORO_CHAT_LOG`` 可改路徑。"""
    override = os.environ.get("DORO_CHAT_LOG", "").strip()
    return Path(override) if override else Path.home() / ".doro" / "chat_log.sqlite3"
