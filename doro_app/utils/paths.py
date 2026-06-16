"""Common filesystem locations used by the Doro application."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
RESOURCES_DIR = PROJECT_ROOT / "res"
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
LIVE2D_MODEL_PATH = RESOURCES_DIR / "Dororong_Live2D_Model_" / "Doro" / "Doro.model3.json"
