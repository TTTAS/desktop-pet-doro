"""Bounded observe/decide/confirm/execute loop without Qt or provider dependencies."""

import json
from collections.abc import Callable

from .models import TaskDecision, ToolCleanupError
from .store import TaskStore
from .tools import ToolRegistry
from .web_tools import TaskRefused


class TaskRunner:
    def __init__(
        self,
        store: TaskStore,
        tools: ToolRegistry,
        ask: Callable,
        confirm: Callable,
        emit: Callable,
        cancelled: Callable,
        *,
        max_steps: int = 24,
    ):
        self.store, self.tools, self.ask = store, tools, ask
        self.confirm, self.emit, self.cancelled = confirm, emit, cancelled
        self.max_steps = max(1, min(max_steps, 48))

    def run(self, task_id: str):
        task = self.store.get(task_id)
        if task["state"] in {"done", "running", "waiting"}:
            raise ValueError("此任務已完成或仍在執行。")
        self.store.update(task_id, "running")
        try:
            self._loop(task_id, task)
        except Exception:
            # Do not expose provider credentials, command output or file data in logs.
            self._finish(task_id, "failed", "任務遇到未預期的錯誤，進度已保留；請查看任務紀錄。")

    def _finish(self, task_id: str, state: str, summary: str):
        self.store.update(task_id, state, summary)
        self.emit(f"任務 {task_id} [{state}]\n{summary}")

    def _loop(self, task_id: str, task: dict):
        errors = 0
        plan = json.loads(task["plan"])
        observed = task["state"] == "queued"
        for index in range(self.max_steps):
            if self.cancelled():
                self._finish(task_id, "cancelled", "已停止；已完成的步驟保留。")
                return
            history = self.store.steps(task_id)
            if len(history) >= 240:
                self._finish(task_id, "blocked", "已達此任務的 240 步總上限，請拆成新任務。")
                return
            # Arguments can include large file bodies. Keep them in the local journal,
            # but only pass bounded observations back to the planner.
            observations = []
            for row in history[-12:]:
                record = {k: row[k] for k in ("tool", "state", "result")}
                parameters = json.loads(row["arguments"])
                record["arguments"] = {k: v for k, v in parameters.items() if k != "text"}
                observations.append(record)
            prompt = json.dumps(
                {
                    "original_user_goal": task["goal"],
                    "plan": plan,
                    "resumed_from": task["state"],
                    "previous_summary": task["summary"],
                    "untrusted_memory": self.store.memory_context(),
                    "untrusted_observations": observations,
                    "available_tools": self.tools.describe(),
                    "remaining_steps": self.max_steps - index,
                },
                ensure_ascii=False,
            )
            decision = self.ask(prompt)
            if self.cancelled():
                self._finish(task_id, "cancelled", "已停止，未執行模型剛回覆的步驟。")
                return
            if not isinstance(decision, TaskDecision):
                self._finish(task_id, "blocked", "模型沒有提供合格的下一步，已停止。")
                return
            # Revalidate even objects constructed without Pydantic validation.
            decision = TaskDecision.model_validate(decision.model_dump())
            if decision.plan:
                plan = decision.plan
                self.store.update(task_id, "running", plan=plan)
                if index == 0:
                    self.emit("任務計畫：\n" + "\n".join(plan))
            if decision.action != "tool":
                if decision.action == "done" and not observed:
                    self._finish(task_id, "blocked", "接續後尚未重新觀察結果，不能宣稱完成。")
                    return
                self._finish(task_id, decision.action, decision.summary)
                return
            if not plan:
                self._finish(task_id, "blocked", "模型未提供執行計畫，已停止。")
                return
            step_id = self.store.intent(task_id, decision.tool, decision.arguments)
            try:
                if not observed and decision.tool not in {
                    "file.list",
                    "file.read",
                    "web.read",
                    "web.search",
                }:
                    raise ValueError("接續任務必須先用唯讀工具觀察目前狀況，不可重播副作用。")
                prepared = self.tools.prepare(decision.tool, decision.arguments)
                if prepared.confirmation:
                    self.store.update(task_id, "waiting")
                    yes = self.confirm(
                        prepared.confirmation + "\n回「好」執行，或「不要」停止任務。"
                    )
                    if not yes or self.cancelled():
                        self.store.result(
                            step_id, "denied", "使用者拒絕、取消或確認逾時；沒有執行。"
                        )
                        self._finish(
                            task_id,
                            "cancelled" if self.cancelled() else "blocked",
                            "這一步沒有執行，任務已停止。",
                        )
                        return
                    self.store.update(task_id, "running")
                if self.cancelled():
                    self.store.result(step_id, "cancelled", "執行前取消。")
                    self._finish(task_id, "cancelled", "已停止。")
                    return
                self.emit(f"任務 {task_id} 第 {index + 1} 步：{decision.tool}")
                result = prepared.run()
                self.store.result(step_id, "ok", result)
                observed = True
                errors = 0
            except TaskRefused:
                self.store.result(step_id, "denied", "使用者拒絕網站步驟，任務已停止。")
                self._finish(
                    task_id,
                    "cancelled" if self.cancelled() else "blocked",
                    "這一步沒有執行，任務已停止。",
                )
                return
            except ToolCleanupError as exc:
                self.store.result(step_id, "pending", str(exc))
                self._finish(task_id, "failed", str(exc))
                return
            except (ValueError, OSError) as exc:
                self.store.result(step_id, "error", str(exc))
                errors += 1
                if errors >= 3:
                    self._finish(task_id, "blocked", "連續三次工具失敗，已停止。請查看任務紀錄。")
                    return
            if self.cancelled():
                self._finish(task_id, "cancelled", "已停止；已完成的步驟保留。")
                return
        self._finish(task_id, "blocked", "已達本輪步數上限；進度已保存，可檢查後接續。")
