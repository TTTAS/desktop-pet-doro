"""Small durable journal, kept outside the tool workspace (one connection per call)."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class TaskStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "tasks.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, goal TEXT NOT NULL, state TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT '[]', summary TEXT NOT NULL DEFAULT '',
                    updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id)
                    ON DELETE CASCADE, tool TEXT NOT NULL, arguments TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending', result TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, text TEXT NOT NULL);
            """)
            db.execute(
                "UPDATE tasks SET state='interrupted' WHERE state IN ('running','waiting','queued')"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, goal: str) -> str:
        if not goal.strip() or len(goal) > 4000:
            raise ValueError("任務目標需為 1–4000 字。")
        task_id = uuid.uuid4().hex[:12]
        with self.connection() as db:
            if db.execute("SELECT count(*) FROM tasks").fetchone()[0] >= 200:
                raise ValueError("已有 200 筆任務，請先刪除不再需要的紀錄。")
            db.execute("INSERT INTO tasks(id,goal,state) VALUES (?,?,'queued')", (task_id, goal))
        return task_id

    def get(self, task_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("找不到這個任務 ID。")
        return dict(row)

    def tasks(self) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM tasks ORDER BY updated DESC, rowid DESC LIMIT 200"
                )
            ]

    def update(self, task_id: str, state: str, summary: str = "", plan: list[str] | None = None):
        with self.connection() as db:
            db.execute(
                "UPDATE tasks SET state=?, summary=?, updated=CURRENT_TIMESTAMP WHERE id=?",
                (state, summary[:4000], task_id),
            )
            if plan is not None:
                db.execute(
                    "UPDATE tasks SET plan=? WHERE id=?",
                    (json.dumps(plan, ensure_ascii=False), task_id),
                )

    def intent(self, task_id: str, tool: str, arguments: dict) -> int:
        with self.connection() as db:
            return db.execute(
                "INSERT INTO steps(task_id,tool,arguments) VALUES (?,?,?)",
                (task_id, tool, json.dumps(arguments, ensure_ascii=False)),
            ).lastrowid

    def result(self, step_id: int, state: str, text: str):
        with self.connection() as db:
            db.execute(
                "UPDATE steps SET state=?, result=? WHERE id=?", (state, text[:6000], step_id)
            )

    def steps(self, task_id: str) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM steps WHERE task_id=? ORDER BY id", (task_id,))
            ]

    def delete(self, task_id: str):
        task = self.get(task_id)
        if task["state"] in {"running", "waiting", "queued"}:
            raise ValueError("請先停止任務，再刪除紀錄。")
        with self.connection() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def remember(self, text: str) -> str:
        if not text.strip() or len(text) > 500:
            raise ValueError("每則記憶需為 1–500 字。")
        memory_id = uuid.uuid4().hex[:12]
        with self.connection() as db:
            if db.execute("SELECT count(*) FROM memories").fetchone()[0] >= 100:
                raise ValueError("已有 100 則記憶，請先忘記不需要的內容。")
            db.execute("INSERT INTO memories VALUES (?,?)", (memory_id, text.strip()))
        return memory_id

    def memories(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM memories ORDER BY rowid")]

    def forget(self, memory_id: str):
        with self.connection() as db:
            if not db.execute("DELETE FROM memories WHERE id=?", (memory_id,)).rowcount:
                raise ValueError("找不到這個記憶 ID。")

    def memory_context(self) -> str:
        selected, size = [], 0
        for item in reversed(self.memories()):
            text = item["text"]
            if size + len(text) + 1 > 6000:
                break
            selected.append(text)
            size += len(text) + 1
        return "\n".join(reversed(selected))

    def report(self, task_id: str) -> str:
        """Human-readable journal for both the panel and explicit chat command."""
        labels = {
            "queued": "等待開始",
            "running": "執行中",
            "waiting": "等待確認",
            "done": "已完成",
            "blocked": "已暫停",
            "failed": "失敗",
            "cancelled": "已取消",
            "interrupted": "上次執行中斷",
            "pending": "結果不確定，接續前需重新觀察",
            "ok": "已執行",
            "error": "執行失敗",
            "denied": "未獲確認，沒有執行",
        }
        task = self.get(task_id)
        lines = [
            f"任務：{task_id}",
            "狀態：" + labels.get(task["state"], task["state"]),
            "目標：" + task["goal"],
            "計畫：",
            *json.loads(task["plan"]),
            "結果：" + task["summary"],
            "",
            "執行紀錄：",
        ]
        for index, step in enumerate(self.steps(task_id), 1):
            lines.extend(
                [
                    f"{index}. {step['tool']} — {labels.get(step['state'], step['state'])}",
                    "參數：" + step["arguments"],
                    "結果：" + step["result"],
                    "",
                ]
            )
        return "\n".join(lines)
