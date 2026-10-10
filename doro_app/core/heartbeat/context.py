"""Files and prompt text for one heartbeat; pure functions, no Qt."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

JOURNAL_SIZE = 8
CHECKLIST_MAX_CHARS = 2000
_WEEKDAYS = "一二三四五六日"

DEFAULT_CHECKLIST = """\
# Doro 心跳清單
# Doro 每次心跳醒來都會讀這份清單，再決定要不要主動找你。
# 用一般的話寫你希望她留意的事，一行一件。以 # 開頭的行是說明，不會給 Doro 看。
# 改完存檔即可，下次心跳就會用新內容。

- 晚上 11 點以後，溫柔提醒我早點睡。
- 我很久沒跟你互動時，可以關心一下我是不是累了。
"""


class ChecklistUnreadable(ValueError):
    """The checklist exists but cannot be decoded; the user has to re-save it."""


@dataclass(frozen=True)
class JournalEntry:
    at: str  # ISO time, local
    line: str  # "" when Doro decided to stay silent


@dataclass(frozen=True)
class HeartbeatContext:
    now: datetime
    seconds_since_interaction: float
    chat: list[tuple[str, str]]  # (speaker, text), oldest first
    checklist: str
    journal: list[JournalEntry]
    page_title: str | None = None


def ensure_checklist(path: Path) -> Path:
    """Create the checklist with examples the first time; never overwrite."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CHECKLIST, encoding="utf-8")
    return path


def read_checklist(path: Path) -> str:
    """Checklist lines for the model: comments and blanks dropped, length capped.

    Raises ``ChecklistUnreadable`` when the file is not UTF-8 (e.g. saved as
    Big5/ANSI); a UTF-8 BOM from Notepad is accepted.
    """
    try:
        text = ensure_checklist(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ChecklistUnreadable("心跳清單不是 UTF-8 編碼，請用 UTF-8 重新存檔") from exc
    except OSError as exc:
        logger.warning("Heartbeat checklist unreadable (%s)", type(exc).__name__)
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    kept = "\n".join(line for line in lines if line.strip() and not line.lstrip().startswith("#"))
    return kept[:CHECKLIST_MAX_CHARS]


def load_journal(path: Path) -> list[JournalEntry]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = [
        JournalEntry(item["at"], item["line"])
        for item in data
        if isinstance(item, dict)
        and isinstance(item.get("at"), str)
        and isinstance(item.get("line"), str)
    ]
    return entries[-JOURNAL_SIZE:]


def append_journal(path: Path, entry: JournalEntry) -> list[JournalEntry]:
    """Add one entry, keep the newest ``JOURNAL_SIZE``, write atomically."""
    entries = (load_journal(path) + [entry])[-JOURNAL_SIZE:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([e.__dict__ for e in entries], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        logger.warning("Heartbeat journal not saved (%s)", type(exc).__name__)
    return entries


def describe_duration(seconds: float) -> str:
    minutes = int(max(0, seconds) // 60)
    if minutes < 1:
        return "不到 1 分鐘"
    if minutes < 60:
        return f"約 {minutes} 分鐘"
    hours, rest = divmod(minutes, 60)
    return f"約 {hours} 小時 {rest} 分鐘" if rest else f"約 {hours} 小時"


def build_prompt(context: HeartbeatContext) -> str:
    """The user message of one heartbeat. Everything here is data, not instructions."""
    now = context.now
    parts = [
        f"現在時間：{now:%Y-%m-%d}（星期{_WEEKDAYS[now.weekday()]}）{now:%H:%M}",
        f"距離使用者上次和你互動：{describe_duration(context.seconds_since_interaction)}",
    ]
    if context.chat:
        chat = "\n".join(f"{who}：{text[:200]}" for who, text in context.chat)
        parts.append(f"最近的聊天：\n{chat}")
    else:
        parts.append("最近的聊天：（沒有）")
    parts.append(f"使用者的心跳清單：\n{context.checklist or '（清單是空的）'}")
    if context.journal:
        journal = "\n".join(
            f"- {_short_time(e.at)} " + (f"說了「{e.line[:120]}」" if e.line else "沒開口")
            for e in context.journal
        )
        parts.append(f"你最近幾次心跳：\n{journal}")
    else:
        parts.append("你最近幾次心跳：（這是第一次）")
    if context.page_title:
        parts.append(f"使用者正在看的分頁標題：{context.page_title[:200]}")
    return "\n\n".join(parts)


def _short_time(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(iso):%m-%d %H:%M}"
    except ValueError:
        return iso
