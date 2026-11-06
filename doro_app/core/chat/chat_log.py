"""`ChatLog` — 本機 SQLite 對話紀錄，給之後練 Doro 的 LoRA 用。

每一輪成功的聊天（使用者那句＋Doro 的完整結構化回覆）存成一列。
只寫本機檔案，不上傳；`scripts/export_lora_dataset.py` 再把它轉成
LLaMA-Factory／Unsloth 吃的 ShareGPT 格式（見 docs/lora-training.md）。

- ``session_id``：同一段連續對話。app 每次啟動、或清除聊天歷史時換新的，
  匯出時同一段會拼成多輪對話。
- ``persona`` 存使用者可改的人設；``system`` 存當下實際送出的完整 system prompt
  （含狀態清單與回覆格式），匯出時可選用哪個。
- 寫入失敗只記 log，不能讓聊天壞掉。
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ...utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL    NOT NULL,
    session_id  TEXT    NOT NULL,
    user        TEXT    NOT NULL,
    reply_json  TEXT    NOT NULL,
    persona     TEXT    NOT NULL DEFAULT '',
    system      TEXT    NOT NULL DEFAULT '',
    model       TEXT    NOT NULL DEFAULT '',
    is_auto     INTEGER NOT NULL DEFAULT 0,
    kind        TEXT    NOT NULL DEFAULT 'chat',
    excluded    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, id);
"""


@dataclass(frozen=True)
class LoggedTurn:
    id: int
    created_at: float
    session_id: str
    user: str
    reply_json: str
    persona: str
    system: str
    model: str
    is_auto: bool
    kind: str
    excluded: bool


class ChatLog:
    """Append-only turn log in one SQLite file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._session_id = self._new_session_id()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def session_id(self) -> str:
        return self._session_id

    def new_session(self) -> None:
        """之後的紀錄算另一段對話（例如使用者清掉聊天歷史）。"""
        self._session_id = self._new_session_id()

    def record(
        self,
        *,
        user: str,
        reply_json: str,
        persona: str = "",
        system: str = "",
        model: str = "",
        is_auto: bool = False,
        kind: str = "chat",
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    (
                        "INSERT INTO turns (created_at, session_id, user, reply_json, persona,"
                        " system, model, is_auto, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        time.time(),
                        self._session_id,
                        user,
                        reply_json,
                        persona,
                        system,
                        model,
                        int(is_auto),
                        kind,
                    ),
                )
        except sqlite3.Error as exc:
            logger.warning(f"Chat log write failed ({self._path}): {exc}")

    def iter_turns(self) -> Iterator[LoggedTurn]:
        """全部紀錄，依 session 內寫入順序排列。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, session_id, user, reply_json, persona, system,"
                " model, is_auto, kind, excluded FROM turns ORDER BY session_id, id"
            ).fetchall()
        for row in rows:
            yield LoggedTurn(*row[:8], bool(row[8]), row[9], bool(row[10]))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Commit on success and always close (sqlite3's own ``with`` doesn't close)."""
        conn = sqlite3.connect(self._path, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _new_session_id() -> str:
        return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
