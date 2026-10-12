import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doro_app.core.heartbeat import controller as heartbeat_module
from doro_app.core.heartbeat.context import load_journal
from doro_app.core.heartbeat.controller import HeartbeatController
from doro_app.core.llm import character_reply_model
from doro_app.core.presence.models import PageEvent

HeartbeatReply = character_reply_model(["happy"], decide_worth_saying=True, name="HeartbeatReply")

TAIPEI = timezone(timedelta(hours=8))


def reply(line, *, worth_saying=True):
    return HeartbeatReply.model_validate(
        {"worth_saying": worth_saying, "state": None, "line": line, "move": None}
    )


class World:
    """Fake surroundings; every flag a test flips is read live by the controller."""

    def __init__(self):
        self.busy = False
        self.quiet = False
        self.since_interaction = 3600.0
        self.system_idle = 5.0
        self.page = None


@pytest.fixture
def heartbeat(tmp_path, qtbot):
    world = World()
    orch = Mock()
    orch.recent_chat_lines.return_value = [("使用者", "嗨")]
    presented = []

    def present(answer, *, should_present, on_present):
        if should_present():
            presented.append(answer.line)
            on_present(answer.line)
        return answer.line

    orch.present_structured_reply.side_effect = present
    config = SimpleNamespace(
        ui=SimpleNamespace(heartbeat_enabled=True, heartbeat_interval_minutes=30)
    )
    controller = HeartbeatController(
        orch,
        config,
        checklist_path=tmp_path / "heartbeat.md",
        journal_path=tmp_path / "journal.json",
        busy=lambda: world.busy,
        quiet=lambda: world.quiet,
        seconds_since_interaction=lambda: world.since_interaction,
        system_idle=lambda: world.system_idle,
        page=lambda: world.page,
        clock=lambda: datetime(2026, 10, 8, 23, 30, tzinfo=TAIPEI),
    )
    yield SimpleNamespace(
        controller=controller,
        orch=orch,
        world=world,
        config=config,
        presented=presented,
        journal=tmp_path / "journal.json",
    )
    controller.shutdown()


def test_enabled_schedules_and_disabled_stops(heartbeat):
    hb = heartbeat
    assert hb.controller.is_scheduled
    assert hb.controller._timer.interval() == 30 * 60 * 1000
    hb.config.ui.heartbeat_enabled = False
    hb.controller.reschedule()
    assert not hb.controller.is_scheduled
    assert hb.controller.beat() == "心跳未開啟"
    hb.orch.make_heartbeat_request.assert_not_called()


def test_interval_change_restarts_timer(heartbeat):
    heartbeat.config.ui.heartbeat_interval_minutes = 5
    heartbeat.controller.reschedule()
    assert heartbeat.controller._timer.interval() == 5 * 60 * 1000


@pytest.mark.parametrize(
    "setup, reason",
    [
        (lambda w: setattr(w, "quiet", True), "安靜陪伴中"),
        (lambda w: setattr(w, "busy", True), "正在忙（聊天、拖曳、選單或動作中）"),
        (lambda w: setattr(w, "since_interaction", 30.0), "剛剛才互動過"),
        (lambda w: setattr(w, "system_idle", 900.0), "使用者不在電腦前"),
    ],
)
def test_skip_rules_never_call_model(heartbeat, setup, reason):
    setup(heartbeat.world)
    assert heartbeat.controller.beat() == reason
    heartbeat.orch.make_heartbeat_request.assert_not_called()


def test_unknown_system_idle_falls_back_to_doro_interaction(heartbeat):
    heartbeat.world.system_idle = None
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    assert heartbeat.controller.beat() is None


def test_only_one_request_at_a_time(heartbeat, qtbot):
    release = threading.Event()

    def slow():
        release.wait(2)
        return reply("", worth_saying=False)

    heartbeat.orch.make_heartbeat_request.return_value = slow
    assert heartbeat.controller.beat() is None
    assert heartbeat.controller.beat() == "上一次心跳還沒結束"
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    assert heartbeat.orch.make_heartbeat_request.call_count == 1


def test_prompt_contains_context(heartbeat, qtbot):
    heartbeat.world.page = PageEvent(1, "https://v.test", "影片網站", "內容")
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    heartbeat.controller.beat()
    prompt = heartbeat.orch.make_heartbeat_request.call_args.args[0]
    assert "23:30" in prompt and "使用者：嗨" in prompt
    assert "11 點" in prompt  # default checklist was created and read
    assert "影片網站" in prompt


def test_silent_reply_shows_nothing_but_is_journaled(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    heartbeat.controller.beat()
    qtbot.waitUntil(lambda: load_journal(heartbeat.journal) != [])
    assert heartbeat.presented == []
    assert load_journal(heartbeat.journal)[0].line == ""
    heartbeat.orch.speak_line.assert_not_called()


def test_spoken_reply_goes_through_character_reply_and_journal(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("該睡了喔")
    heartbeat.controller.beat()
    qtbot.waitUntil(lambda: heartbeat.presented == ["該睡了喔"])
    assert load_journal(heartbeat.journal)[0].line == "該睡了喔"
    assert "心跳完成" in heartbeat.controller.last_status


def test_interaction_while_waiting_drops_the_result(heartbeat, qtbot):
    release = threading.Event()

    def slow():
        release.wait(2)
        return reply("我來了")

    heartbeat.orch.make_heartbeat_request.return_value = slow
    heartbeat.controller.beat()
    heartbeat.controller.interrupt()  # the user started chatting
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    assert heartbeat.presented == []
    assert load_journal(heartbeat.journal) == []


def test_reply_waits_while_doro_is_busy_then_speaks(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("嗨嗨")
    heartbeat.controller.beat()
    heartbeat.world.busy = True
    qtbot.waitUntil(lambda: heartbeat.controller._pending is not None)
    assert heartbeat.presented == []
    heartbeat.world.busy = False
    qtbot.waitUntil(lambda: heartbeat.presented == ["嗨嗨"], timeout=3000)


def test_quiet_mode_drops_waiting_reply(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("嗨嗨")
    heartbeat.controller.beat()
    heartbeat.world.busy = True
    qtbot.waitUntil(lambda: heartbeat.controller._pending is not None)
    heartbeat.world.quiet = True
    heartbeat.world.busy = False
    qtbot.waitUntil(lambda: heartbeat.controller._pending is None, timeout=3000)
    assert heartbeat.presented == []


def test_waiting_reply_expires(heartbeat, qtbot, monkeypatch):
    monkeypatch.setattr(heartbeat_module, "PENDING_TTL_SECONDS", -1)
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("嗨嗨")
    heartbeat.world.busy = False
    heartbeat.controller.beat()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    assert heartbeat.presented == []


def test_model_failure_is_quiet(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: None
    heartbeat.controller.beat()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    assert heartbeat.presented == []
    assert "沒有拿到" in heartbeat.controller.last_status


def test_settings_error_is_reported_as_skip(heartbeat):
    heartbeat.orch.make_heartbeat_request.side_effect = RuntimeError("no settings")
    assert heartbeat.controller.beat() == "模型設定暫時無法使用"


def test_manual_beat_ignores_presence_checks_but_not_quiet(heartbeat, qtbot):
    hb = heartbeat
    hb.config.ui.heartbeat_enabled = False
    hb.world.since_interaction = 1.0
    hb.world.system_idle = 900.0
    hb.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    hb.controller.beat_now()
    qtbot.waitUntil(lambda: hb.orch.speak_line.called)
    hb.orch.speak_line.assert_called_once_with("（Doro 想了想，決定先不打擾你）")

    hb.orch.speak_line.reset_mock()
    hb.world.quiet = True
    hb.controller.beat_now()
    hb.orch.speak_line.assert_called_once_with("（心跳先跳過：安靜陪伴中）")
    assert hb.orch.make_heartbeat_request.call_count == 1


def test_busy_tick_retries_soon_and_success_restarts_cadence(heartbeat):
    hb = heartbeat
    hb.world.busy = True
    hb.controller._on_timer()
    assert hb.controller._retry.isActive()
    hb.world.busy = False
    hb.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    hb.controller._on_timer()
    assert not hb.controller._retry.isActive()
    assert hb.controller.is_scheduled


def test_shutdown_stops_everything(heartbeat):
    heartbeat.controller.shutdown()
    assert not heartbeat.controller.is_scheduled
    assert heartbeat.controller.beat(manual=True) == "已關閉"


def _slow(answer_factory):
    release = threading.Event()

    def ask():
        release.wait(2)
        return answer_factory()

    return release, ask


@pytest.mark.parametrize("next_page", [PageEvent(2, "https://b.test", "B", "b"), None])
def test_page_change_while_waiting_drops_reply(heartbeat, qtbot, next_page):
    """Review #2: a reply about page A must not be spoken once the user is on B."""
    heartbeat.world.page = PageEvent(1, "https://a.test", "A", "a")
    release, ask = _slow(lambda: reply("A 頁好有趣"))
    heartbeat.orch.make_heartbeat_request.return_value = ask
    heartbeat.controller.beat()
    heartbeat.world.page = next_page
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    qtbot.wait(50)
    assert heartbeat.presented == []


def test_page_change_while_reply_waits_for_busy_drops_it(heartbeat, qtbot):
    heartbeat.world.page = PageEvent(1, "https://a.test", "A", "a")
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("A 頁好有趣")
    heartbeat.controller.beat()
    heartbeat.world.busy = True
    qtbot.waitUntil(lambda: heartbeat.controller._pending is not None)
    heartbeat.world.page = PageEvent(2, "https://b.test", "B", "b")
    heartbeat.world.busy = False
    qtbot.waitUntil(lambda: heartbeat.controller._pending is None, timeout=3000)
    assert heartbeat.presented == []


def test_beat_without_page_is_not_dropped_when_a_page_appears(heartbeat, qtbot):
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("該喝水了")
    heartbeat.controller.beat()
    heartbeat.world.page = PageEvent(2, "https://b.test", "B", "b")
    qtbot.waitUntil(lambda: heartbeat.presented == ["該喝水了"])


@pytest.mark.parametrize("cancel", ["quiet", "interrupt"])
def test_failed_manual_beat_respects_cancel_and_quiet(heartbeat, qtbot, cancel):
    """Review #4: no failure bubble after the user cancelled or went quiet."""
    release, ask = _slow(lambda: None)
    heartbeat.orch.make_heartbeat_request.return_value = ask
    heartbeat.controller.beat_now()
    if cancel == "quiet":
        heartbeat.world.quiet = True
    else:
        heartbeat.controller.interrupt()
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    qtbot.wait(50)
    heartbeat.orch.speak_line.assert_not_called()


def test_silent_manual_beat_after_quiet_says_nothing(heartbeat, qtbot):
    release, ask = _slow(lambda: reply("", worth_saying=False))
    heartbeat.orch.make_heartbeat_request.return_value = ask
    heartbeat.controller.beat_now()
    heartbeat.world.quiet = True
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    qtbot.wait(50)
    heartbeat.orch.speak_line.assert_not_called()


def test_non_utf8_checklist_skips_instead_of_raising(heartbeat, tmp_path):
    """Review #5: a Big5/ANSI checklist must not escape the Qt callback."""
    (tmp_path / "heartbeat.md").write_bytes("- 晚上提醒我睡覺".encode("big5"))
    reason = heartbeat.controller.beat()
    assert reason is not None and "UTF-8" in reason
    heartbeat.orch.make_heartbeat_request.assert_not_called()
    heartbeat.controller.beat_now()
    assert "UTF-8" in heartbeat.orch.speak_line.call_args.args[0]


# Review of 9c3fb52: every manual notice must wait for the bubble like a reply does.


@pytest.mark.parametrize(
    "answer, notice",
    [(lambda: None, "（心跳沒有拿到模型回覆）"), (lambda: reply("", worth_saying=False), None)],
    ids=["failure", "silent"],
)
def test_manual_result_notice_waits_for_busy_bubble(heartbeat, qtbot, answer, notice):
    release, ask = _slow(answer)
    heartbeat.orch.make_heartbeat_request.return_value = ask
    heartbeat.controller.beat_now()
    heartbeat.world.busy = True  # an idle line or tab reaction appeared meanwhile
    release.set()
    qtbot.waitUntil(lambda: not heartbeat.controller._running)
    qtbot.wait(100)
    heartbeat.orch.speak_line.assert_not_called()
    heartbeat.world.busy = False
    qtbot.waitUntil(lambda: heartbeat.orch.speak_line.called, timeout=3000)
    shown = heartbeat.orch.speak_line.call_args.args[0]
    assert shown == (notice or "（Doro 想了想，決定先不打擾你）")
    heartbeat.orch.speak_line.assert_called_once()


def test_manual_skip_notice_does_not_cover_the_bubble_that_made_it_busy(heartbeat, qtbot):
    heartbeat.world.busy = True
    heartbeat.controller.beat_now()
    qtbot.wait(100)
    heartbeat.orch.speak_line.assert_not_called()
    heartbeat.world.busy = False
    qtbot.waitUntil(lambda: heartbeat.orch.speak_line.called, timeout=3000)
    assert "正在忙" in heartbeat.orch.speak_line.call_args.args[0]


def test_notice_is_dropped_when_busy_too_long(heartbeat, qtbot, monkeypatch):
    monkeypatch.setattr(heartbeat_module, "NOTICE_TTL_SECONDS", 0.2)
    heartbeat.world.busy = True
    heartbeat.controller.beat_now()
    qtbot.waitUntil(lambda: heartbeat.controller._notice is None, timeout=3000)
    heartbeat.world.busy = False
    qtbot.wait(700)
    heartbeat.orch.speak_line.assert_not_called()


@pytest.mark.parametrize("cancel", ["quiet", "interrupt"])
def test_waiting_notice_is_dropped_on_cancel(heartbeat, qtbot, cancel):
    heartbeat.world.busy = True
    heartbeat.controller.beat_now()
    if cancel == "quiet":
        heartbeat.world.quiet = True
    else:
        heartbeat.controller.interrupt()
    heartbeat.world.busy = False
    qtbot.wait(700)
    heartbeat.orch.speak_line.assert_not_called()


def test_waiting_notice_does_not_block_the_next_beat(heartbeat):
    heartbeat.world.busy = True
    heartbeat.controller.beat_now()
    heartbeat.world.busy = False
    heartbeat.orch.make_heartbeat_request.return_value = lambda: reply("", worth_saying=False)
    assert heartbeat.controller.beat(manual=True) is None
