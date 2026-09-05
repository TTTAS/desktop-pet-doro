"""網頁能力（第 1 層：讀）。

doro 用「真的瀏覽器」打開你給的網址、把內容讀進來，再交給聊天 AI 幫你摘要／回答。

這個資料夾內的房間：
- ``intent.py``：聽懂「幫我讀這頁 <網址>」這類指令，抽出網址和你的問題。
- ``reader.py``：真正用 Playwright 開瀏覽器、讀網頁文字（門）。
- ``worker.py``：把「開瀏覽器讀網頁」這件慢事丟到背景執行緒，不卡住畫面。

門（外面要用就從這裡進來）：
- ``parse_web_read_command`` … 判斷一句話是不是「讀網頁」指令。
- ``WebPageReader`` … 實際把網頁讀成文字。
"""

from __future__ import annotations

from .intent import (
    WebReadRequest,
    is_affirmative,
    is_stop,
    parse_login_action,
    parse_operate_action,
    parse_operate_command,
    parse_read_action,
    parse_read_current_command,
    parse_verify_action,
    parse_web_read_command,
)
from .reader import WebPageReader, WebReadResult

__all__ = [
    "WebReadRequest",
    "parse_web_read_command",
    "parse_read_action",
    "parse_read_current_command",
    "parse_operate_command",
    "parse_operate_action",
    "parse_login_action",
    "parse_verify_action",
    "is_affirmative",
    "is_stop",
    "WebPageReader",
    "WebReadResult",
]
