"""Use real files and SQLite to check effects, recovery, refusal and cancellation."""

import json
import os
import threading

import pytest

from doro_app.core.agent.engine import TaskRunner
from doro_app.core.agent.models import TaskDecision
from doro_app.core.agent.store import TaskStore
from doro_app.core.agent.tools import FilePath, Workspace, WriteFile, local_tools


@pytest.fixture
def context(tmp_path):
    store = TaskStore(tmp_path / "private")
    workspace = Workspace(tmp_path / "work")
    cancelled = threading.Event()
    registry = local_tools(workspace, cancelled.is_set)
    return store, workspace, cancelled, registry


def run(context, decisions, *, confirm=lambda _: True, goal="整理檔案", task_id=None, max_steps=24):
    store, _, cancelled, registry = context
    task_id = task_id or store.create(goal)
    prompts, output = [], []
    iterator = iter(decisions)

    def ask(prompt):
        prompts.append(json.loads(prompt))
        return next(iterator)

    TaskRunner(
        store, registry, ask, confirm, output.append, cancelled.is_set, max_steps=max_steps
    ).run(task_id)
    return task_id, prompts, output


def decision(tool, **arguments):
    return TaskDecision(
        action="tool", tool=tool, arguments=arguments, plan=["讀取來源", "整理並驗證結果"]
    )


def test_read_write_readback_and_durable_journal(context):
    store, workspace, _, _ = context
    (workspace.root / "notes.txt").write_text("買牛奶\n完成報告", encoding="utf-8")
    confirmations = []
    task_id, prompts, output = run(
        context,
        [
            decision("file.read", path="notes.txt"),
            decision("file.write", path="todo.md", text="- 買牛奶\n- 完成報告\n"),
            decision("file.read", path="todo.md"),
            TaskDecision(action="done", summary="已建立 todo.md 並讀回確認。"),
        ],
        confirm=lambda text: confirmations.append(text) or True,
    )
    assert (workspace.root / "todo.md").read_text(encoding="utf-8") == "- 買牛奶\n- 完成報告\n"
    assert len(confirmations) == 1 and "+- 完成報告" in confirmations[0]
    assert "買牛奶" in prompts[1]["untrusted_observations"][0]["result"]
    assert prompts[1]["untrusted_observations"][0]["arguments"] == {"path": "notes.txt"}
    reopened = TaskStore(store.path.parent)
    assert reopened.get(task_id)["state"] == "done"
    assert [s["state"] for s in reopened.steps(task_id)] == ["ok", "ok", "ok"]
    assert task_id in output[-1]


@pytest.mark.parametrize(
    "path", ["../secret", "/etc/passwd", "sub/../../secret", "C:/secret", "a\\secret"]
)
def test_paths_cannot_escape(context, path):
    _, workspace, _, _ = context
    with pytest.raises(ValueError):
        workspace.path(path)


@pytest.mark.parametrize(
    "path", [".. /secret", "CON", "nul.txt", "sub/LPT1", "file. ", "file\nname"]
)
def test_nonportable_device_and_ambiguous_paths_are_refused(context, path):
    _, workspace, _, _ = context
    with pytest.raises(ValueError):
        workspace.path(path)


@pytest.mark.parametrize("kind", ["file", "parent", "hard"])
def test_links_cannot_expose_outside_files(context, tmp_path, kind):
    _, workspace, _, _ = context
    outside = tmp_path / "secret"
    outside.write_text("private")
    link = workspace.root / "link"
    if kind == "hard":
        os.link(outside, link)
    else:
        link.symlink_to(
            outside if kind == "file" else tmp_path, target_is_directory=kind == "parent"
        )
    with pytest.raises(ValueError):
        workspace.read(FilePath(path="link/secret" if kind == "parent" else "link"))
    assert outside.read_text(encoding="utf-8") == "private"


@pytest.mark.parametrize("data", [b"\0bad", b"a" * 65537, b"\xff\xfe"])
def test_bad_files_are_refused(context, data):
    _, workspace, _, _ = context
    (workspace.root / "bad").write_bytes(data)
    with pytest.raises(ValueError):
        workspace.read(FilePath(path="bad"))


@pytest.mark.parametrize("initial", [None, "old"])
def test_confirmation_cannot_overwrite_a_changed_file(context, initial):
    _, workspace, _, _ = context
    path = workspace.root / "draft"
    if initial is not None:
        path.write_text(initial)
    prepared = workspace.write(WriteFile(path="draft", text="model"))
    path.write_text("human")
    with pytest.raises(ValueError, match="變更"):
        prepared.run()
    assert path.read_text(encoding="utf-8") == "human"


def test_link_swap_during_confirmation_is_refused(context, tmp_path):
    _, workspace, _, _ = context
    prepared = workspace.write(WriteFile(path="draft", text="model"))
    outside = tmp_path / "outside"
    outside.write_text("human")
    (workspace.root / "draft").symlink_to(outside)
    with pytest.raises(ValueError):
        prepared.run()
    assert outside.read_text(encoding="utf-8") == "human"


def test_refusal_stops_entire_task_without_asking_for_another_tool(context):
    store, workspace, _, _ = context
    task_id, prompts, _ = run(
        context, [decision("file.write", path="out", text="x")], confirm=lambda _: False
    )
    assert not (workspace.root / "out").exists()
    assert len(prompts) == 1
    assert store.get(task_id)["state"] == "blocked"
    assert store.steps(task_id)[0]["state"] == "denied"


@pytest.mark.parametrize("when", ["ask", "confirm", "before"])
def test_cancel_stops_late_decision_or_confirmation(context, when):
    store, workspace, cancelled, registry = context
    task_id = store.create("write")
    calls = []

    def ask(_):
        if when == "ask":
            cancelled.set()
        return decision("file.write", path="out", text="x")

    def confirm(_):
        calls.append(True)
        cancelled.set()
        return True

    if when == "before":
        cancelled.set()
    TaskRunner(store, registry, ask, confirm, lambda _: None, cancelled.is_set).run(task_id)
    assert store.get(task_id)["state"] == "cancelled"
    assert not (workspace.root / "out").exists()
    assert len(calls) == (1 if when == "confirm" else 0)


def test_invalid_decision_and_unregistered_tool_never_execute(context):
    store, workspace, _, _ = context
    task_id, _, _ = run(context, [None])
    assert store.get(task_id)["state"] == "blocked"
    task_id, prompts, _ = run(context, [decision("host.shell", argv=["rm", "-rf", "/"])] * 3)
    assert len(prompts) == 3 and store.get(task_id)["state"] == "blocked"
    assert not list(workspace.root.iterdir())


def test_step_budget_and_missing_plan(context):
    store, _, _, _ = context
    task_id, prompts, _ = run(context, [decision("file.list")] * 2, max_steps=2)
    assert len(prompts) == 2 and "上限" in store.get(task_id)["summary"]
    task_id, _, _ = run(context, [TaskDecision(action="tool", tool="file.list")])
    assert not store.steps(task_id)
    assert "計畫" in store.get(task_id)["summary"]


def test_recovery_keeps_uncertain_intent_and_requires_observation(context):
    store, workspace, cancelled, registry = context
    task_id = store.create("整理資料")
    store.update(task_id, "running", plan=["寫入結果"])
    store.intent(task_id, "file.write", {"path": "out", "text": "old"})
    (workspace.root / "out").write_text("old")  # crash after effect, before result
    store = TaskStore(store.path.parent)
    assert store.get(task_id)["state"] == "interrupted"
    confirms = []
    task_id, prompts, _ = run(
        (store, workspace, cancelled, registry),
        [
            decision("file.write", path="out", text="duplicate"),
            decision("file.read", path="out"),
            TaskDecision(action="done", summary="確認先前已寫入。"),
        ],
        task_id=task_id,
        confirm=lambda text: confirms.append(text) or True,
    )
    assert not confirms
    assert prompts[0]["untrusted_observations"][0]["state"] == "pending"
    assert prompts[0]["untrusted_observations"][0]["arguments"] == {"path": "out"}
    assert (workspace.root / "out").read_text(encoding="utf-8") == "old"
    assert store.get(task_id)["state"] == "done"


def test_resumed_task_cannot_claim_done_without_observation(context):
    store, _, _, _ = context
    task_id = store.create("verify")
    store.update(task_id, "interrupted")
    run(context, [TaskDecision(action="done", summary="done")], task_id=task_id)
    assert store.get(task_id)["state"] == "blocked"


def test_memory_is_explicit_and_task_deletion_removes_steps(context):
    store, workspace, _, _ = context
    memory_id = store.remember("偏好繁體中文")
    task_id, prompts, _ = run(
        context, [decision("file.list"), TaskDecision(action="done", summary="已查看。")]
    )
    assert prompts[0]["untrusted_memory"] == "偏好繁體中文"
    assert len(store.memories()) == 1
    store.delete(task_id)
    assert not store.steps(task_id) and not store.tasks()
    store.forget(memory_id)
    assert TaskStore(store.path.parent).memory_context() == ""
    assert workspace.root.is_dir()


def test_cannot_delete_live_task_or_overflow_memory(context):
    store, _, _, _ = context
    task_id = store.create("live")
    with pytest.raises(ValueError):
        store.delete(task_id)
    with pytest.raises(ValueError):
        store.remember("x" * 501)


@pytest.mark.parametrize(
    "arguments",
    [{"path": "out", "text": "hi", "force": True}, {"path": 5}, {"path": "out", "text": None}],
)
def test_tool_arguments_are_strict(context, arguments):
    *_, registry = context
    with pytest.raises(ValueError):
        registry.prepare("file.write", arguments)


def test_uncertain_container_cleanup_stops_instead_of_retrying(context):
    from doro_app.core.agent.models import ToolCleanupError
    from doro_app.core.agent.tools import Arguments, PreparedTool

    store, _, _, registry = context

    def uncertain():
        raise ToolCleanupError("無法確認容器 doro-task-fixture 已清理")

    registry.add("test.cleanup", "fixture", Arguments, lambda _: PreparedTool(uncertain))
    task_id, prompts, _ = run(context, [decision("test.cleanup")])
    assert len(prompts) == 1
    assert store.get(task_id)["state"] == "failed"
    assert "doro-task-fixture" in store.get(task_id)["summary"]
    assert store.steps(task_id)[0]["state"] == "pending"
