"""網頁能力（讀 / 查證 / 操作）。

doro 用瀏覽器與搜尋 API 幫你做三件事：

- **讀**（第 1 層）：打開你給的網址、把內容讀進來交給聊天 AI 摘要／回答
  （``intent.py`` 聽指令、``reader.py`` 用 Playwright 讀、``worker.py`` 丟背景）。
- **查證**（第 2 層）：``verify.py`` 的 ``VerifyPipeline``——**用搜尋 API
  （Tavily 主／ddgs 備援，見 ``search_providers.py``）找來源，摘要夠就直接比對、
  不夠才用瀏覽器補讀**，多來源一起比對後誠實回報。已不再爬 Bing HTML。
- **操作**（第 3 層）：``operator.py`` 的 ``WebOperator`` 點／填／送出（送出類先問你）。

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
