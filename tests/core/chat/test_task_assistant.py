"""Task routing must originate from a user, not a page or background reply."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.chat.chat_reply import chat_reply_model
from doro_app.core.chat.orchestrator import ChatOrchestrator
from doro_app.core.web.runtime import WebRuntime
from doro_app.ui.dialogs.task_assistant_dialog import TaskAssistantDialog
from doro_app.utils.config_manager import ConfigManager


@pytest.fixture
def orch(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        ChatOrchestrator, "_default_web_profile_dir", staticmethod(lambda: tmp_path / "web")
    )
    controller = Mock()
    controller.is_inflight = False
    controller.settings = SimpleNamespace(
        server_url="http://127.0.0.1:1234",
        endpoint_path="/v1/chat/completions",
        model="test",
        api_key="",
        timeout_seconds=10,
        temperature=0.1,
        max_tokens=900,
        structured_mode="auto",
        system_prompt="Doro",
    )
    config = ConfigManager(tmp_path / "config.ini")
    orchestrator = ChatOrchestrator(
        controller, Mock(), Mock(), web_runtime=Mock(), config_manager=config
    )
    orchestrator._state_service.visible_state_keys.return_value = ["idle"]
    return orchestrator


def enable(orch):
    orch._config_manager.update_automation(task_assistant_enabled=True)


def reply():
    return chat_reply_model(["idle"]).model_validate(
        {"line": "開始", "tool": {"kind": "task", "goal": "模型擅自擴大的目標"}}
    )


def test_disabled_task_never_starts_or_creates_data(orch):
    assert orch.send_message("/任務 讀 notes.txt")
    orch._web_runtime.submit_task.assert_not_called()
    assert not orch.task_directory.exists()
    assert not orch.is_web_busy


def test_invalid_settings_do_not_leave_an_unresumable_queued_task(orch):
    enable(orch)
    orch.settings.max_tokens = "invalid"
    assert orch.send_message("/任務 讀 notes.txt")
    assert not orch.task_store().tasks()
    assert not orch.is_web_busy


def test_natural_language_task_keeps_user_goal_not_model_rewrite(orch):
    enable(orch)
    orch._last_user_text = "讀 notes.txt 整理重點"
    orch._on_request_succeeded(reply(), False)
    task = orch.task_store().tasks()[0]
    assert task["goal"] == "讀 notes.txt 整理重點"
    assert orch.is_web_busy
    assert orch._web_runtime.submit_task.call_args.kwargs["ask_web"] is None
    orch._on_op_finished()
    assert not orch.is_web_busy


@pytest.mark.parametrize("source", ["auto", "page"])
def test_untrusted_or_automatic_reply_cannot_start_task(orch, source):
    enable(orch)
    orch._expect_web_answer = source == "page"
    orch._on_request_succeeded(reply(), source == "auto")
    orch._web_runtime.submit_task.assert_not_called()
    assert not orch.task_directory.exists()


def test_commands_manage_memory_and_tasks_without_llm(orch):
    assert orch.send_message("/記住 我偏好繁體中文")
    memory = orch.task_store().memories()[0]
    assert orch.task_memory_context() == ""
    enable(orch)
    assert "繁體中文" in orch.task_memory_context()
    assert orch.send_message("/忘記 " + memory["id"])
    assert orch.task_memory_context() == ""
    orch._controller.start_request.assert_not_called()
    assert orch.send_message("/任務 讀 notes.txt")
    task = orch.task_store().tasks()[0]
    orch.send_message("停")
    orch._web_runtime.request_cancel.assert_called_once()
    orch.task_store().update(task["id"], "cancelled")
    orch._on_op_finished()
    assert orch.send_message("/繼續 " + task["id"])
    assert len(orch.task_store().tasks()) == 1


def test_switch_round_trip_preserves_other_automation_settings(orch):
    cm = orch._config_manager
    cm.update_automation(web_operation_enabled=True, task_assistant_enabled=True)
    cm.update_automation(mouse_enabled=False)
    cm.save()
    loaded = ConfigManager(cm._settings.fileName())
    assert loaded.automation.task_assistant_enabled
    assert loaded.automation.web_operation_enabled
    with pytest.raises(ValueError):
        loaded.update_automation(task_assistant_enabled="yes")


def test_task_panel_views_deletes_and_forgets_real_records(orch, qtbot):
    store = orch.task_store()
    task_id = store.create("demo")
    store.update(task_id, "done", "完成")
    store.intent(task_id, "file.read", {"path": "notes.txt"})
    store.remember("繁體中文")
    panel = TaskAssistantDialog(orch)
    qtbot.addWidget(panel)
    assert task_id in panel.journal.toPlainText()
    assert panel.memory_list.count() == 1
    panel.memory_list.setCurrentRow(0)
    panel._forget()
    assert not store.memories()
    panel._delete_task()
    assert not store.tasks() and not store.steps(task_id)


def test_runtime_failure_finishes_and_does_not_launch_browser(orch):
    store = orch.task_store()
    task_id = store.create("test")
    runtime = WebRuntime(orch.task_directory / "profile")
    runtime._get_session = Mock(side_effect=AssertionError("must not open browser"))
    finished = []
    runtime.op_finished.connect(lambda: finished.append(True))
    runtime._do_task(task_id, store, orch.task_directory / "workspace", lambda _: None, None, None)
    assert finished == [True]
    assert store.get(task_id)["state"] == "blocked"
    runtime._get_session.assert_not_called()


def test_real_runtime_queue_delivers_completion_to_gui(orch, qtbot):
    from doro_app.core.agent.models import TaskDecision

    store = orch.task_store()
    task_id = store.create("列出工作目錄")
    runtime = WebRuntime(orch.task_directory / "profile")
    steps = iter(
        [
            TaskDecision(action="tool", tool="file.list", plan=["列出目錄"]),
            TaskDecision(action="done", summary="已列出。"),
        ]
    )
    runtime.start()
    try:
        with qtbot.waitSignal(runtime.op_finished, timeout=5000):
            runtime.submit_task(
                task_id, store, orch.task_directory / "workspace", lambda _: next(steps)
            )
        assert store.get(task_id)["state"] == "done"
        assert runtime._session is None
    finally:
        runtime.shutdown()
        runtime._thread.join(timeout=5)
    assert not runtime._thread.is_alive()
