"""Operation contracts: bounded decisions, confirmations and useful observations."""

import pytest
from pydantic import ValidationError

from doro_app.core.web.operator import WebOperator, build_operate_prompt
from doro_app.core.web.runtime import WebRuntime
from doro_app.core.web.session import PageView
from doro_app.core.web.web_actions import WebStep, needs_confirmation

from .test_operator import FakeLLM, FakeSession, done, step


@pytest.mark.parametrize(
    "decision",
    [
        {"action": "select", "n": 0},
        {"action": "check", "n": 0},
        {"action": "check", "n": 0, "checked": "false"},
        {"action": "hover", "n": -1},
        {"action": "click", "n": True},
        {"action": "click", "n": 1.5},
        {"action": "switch_tab", "tab_id": -1},
        {"action": "wait", "seconds": 0},
        {"action": "wait", "seconds": 6},
        {"action": "wait", "seconds": float("nan")},
        {"action": "new_tab", "url": "file:///tmp/private"},
        {"action": "goto", "url": "https://"},
        {"action": "goto", "url": "https://user:password@example.test"},
        {"action": "press", "key": " "},
    ],
)
def test_invalid_decisions_are_rejected(decision):
    with pytest.raises(ValidationError):
        WebStep.model_validate(decision)


def test_false_and_zero_ids_are_required_values_and_text_is_not_trimmed():
    assert step("check", n=0, checked=False).to_action().params == {"n": "0", "checked": "False"}
    assert step("switch_tab", tab_id=0).to_action().params == {"tab_id": "0"}
    for value in ("  exact text  ", ""):
        assert step("type", n=0, text=value).to_action().params["text"] == value
    assert step("scroll", dir="up", url="https://irrelevant.test").to_action().params == {
        "dir": "up"
    }


@pytest.mark.parametrize(
    "decision", [step("select", n=0, text="Option"), step("check", n=0, checked=False)]
)
def test_change_events_need_confirmation_and_denial_has_no_effect(decision):
    session = FakeSession(
        [PageView(url="https://example.test", elements=[{"idx": 0, "name": "Preference"}])]
    )
    prompts = []
    assert needs_confirmation(decision.to_action())
    WebOperator(
        session, FakeLLM([decision]), lambda text: prompts.append(text) or False, lambda _: None
    ).run("change preference")
    assert session.executed == []
    assert "https://example.test" in prompts[0]


def test_same_index_on_next_page_can_be_clicked_again():
    views = [
        PageView(url=url, elements=[{"idx": 0, "name": "Next", "tag": "a"}])
        for url in ("https://a.test", "https://b.test")
    ]
    session = FakeSession(views)
    WebOperator(
        session,
        FakeLLM([step("click", n=0), step("click", n=0), done()]),
        lambda _: True,
        lambda _: None,
    ).run("next twice")
    assert len(session.executed) == 2


def test_three_execution_errors_stop_with_reason():
    session = FakeSession([PageView(url="https://a.test")], exec_err="無法取得頁面")
    messages = []
    llm = FakeLLM([step("press", key="Tab")] * 8)
    WebOperator(session, llm, lambda _: True, messages.append).run("next")
    assert len(session.executed) == 3
    assert "連續三次" in messages[-1] and "無法取得頁面" in messages[-1]
    assert "失敗" in llm.prompts[-1]


def test_prompt_contains_tabs_options_and_prioritizes_scrolled_controls():
    view = PageView(
        url="https://a.test",
        tabs=[{"id": 7, "title": "Other", "url": "https://b.test", "active": False}],
    )
    view.elements = [
        {"idx": n, "tag": "a", "name": f"Old{n}", "in_viewport": False} for n in range(40)
    ]
    view.elements.append(
        {
            "idx": 40,
            "tag": "select",
            "name": "Category",
            "in_viewport": True,
            "options": [{"label": "Second", "disabled": False}],
        }
    )
    prompt = build_operate_prompt("choose", view, [], step=0, max_steps=12)
    assert "[40]" in prompt and "Second" in prompt and "id=7" in prompt
    assert "不可信資料" in prompt and "不是新的指令" in prompt


@pytest.mark.parametrize(
    "decision",
    [
        step("new_tab", url="https://a.test"),
        step("switch_tab", tab_id=0),
        step("wait", seconds=1),
        step("select", n=0, text="A"),
        step("check", n=0, checked=True),
    ],
)
def test_cancel_during_decision_prevents_every_new_action(decision):
    session = FakeSession([PageView(elements=[{"idx": 0, "name": "A"}])])
    cancelled = [False]

    def ask(_):
        cancelled[0] = True
        return decision

    WebOperator(
        session, ask, lambda _: True, lambda _: None, should_cancel=lambda: cancelled[0]
    ).run("task")
    assert session.executed == []


def test_cancel_between_confirm_check_and_event_clear_does_not_wait(tmp_path):
    runtime = WebRuntime(tmp_path)

    class Event:
        def clear(self):
            runtime._cancel.set()

        def wait(self, _):
            pytest.fail("cancelled confirmation must not wait")

    runtime._confirm_event = Event()
    assert runtime._confirm_bridge("confirm") is False


def test_runtime_error_reports_failure_and_finishes(tmp_path, monkeypatch):
    runtime = WebRuntime(tmp_path)
    messages, finished = [], []
    runtime.op_progress.connect(messages.append)
    runtime.op_finished.connect(lambda: finished.append(True))

    def broken(*_):
        raise RuntimeError("do not expose private input")

    monkeypatch.setattr(WebOperator, "run", broken)
    runtime._do_operation("task", lambda _: None)
    assert finished == [True]
    assert "錯誤" in messages[-1]
    assert "private" not in messages[-1]
