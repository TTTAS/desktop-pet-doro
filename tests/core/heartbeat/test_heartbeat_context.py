from datetime import datetime, timedelta, timezone

from doro_app.core.heartbeat.context import (
    DEFAULT_CHECKLIST,
    JOURNAL_SIZE,
    HeartbeatContext,
    JournalEntry,
    append_journal,
    build_prompt,
    describe_duration,
    ensure_checklist,
    load_journal,
    read_checklist,
)

TAIPEI = timezone(timedelta(hours=8))


def test_checklist_is_created_once_and_comments_are_dropped(tmp_path):
    path = tmp_path / "sub" / "heartbeat.md"

    text = read_checklist(path)

    assert path.read_text(encoding="utf-8") == DEFAULT_CHECKLIST
    assert "11 點" in text and "#" not in text
    path.write_text("# 說明\n\n- 下午提醒我喝水\n", encoding="utf-8")
    ensure_checklist(path)
    assert read_checklist(path) == "- 下午提醒我喝水"


def test_journal_keeps_newest_entries_across_reloads(tmp_path):
    path = tmp_path / "journal.json"
    for i in range(JOURNAL_SIZE + 3):
        append_journal(path, JournalEntry(f"2026-10-08T10:{i:02d}:00", f"第{i}句"))

    entries = load_journal(path)

    assert len(entries) == JOURNAL_SIZE
    assert entries[-1].line == f"第{JOURNAL_SIZE + 2}句"
    assert entries[0].line == "第3句"


def test_broken_journal_reads_as_empty(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text("{oops", encoding="utf-8")
    assert load_journal(path) == []
    path.write_text('[{"at": "x"}, {"at": "2026-10-08T10:00:00", "line": ""}]', encoding="utf-8")
    assert load_journal(path) == [JournalEntry("2026-10-08T10:00:00", "")]


def test_prompt_contains_every_part():
    prompt = build_prompt(
        HeartbeatContext(
            now=datetime(2026, 10, 8, 23, 15, tzinfo=TAIPEI),
            seconds_since_interaction=42 * 60,
            chat=[("使用者", "晚安前再聊一下")],
            checklist="- 晚上提醒我睡覺",
            journal=[
                JournalEntry("2026-10-08T22:45:00", "要喝水喔"),
                JournalEntry("2026-10-08T22:15:00", ""),
            ],
            page_title="影片網站",
        )
    )

    assert "2026-10-08（星期四）23:15" in prompt
    assert "約 42 分鐘" in prompt
    assert "使用者：晚安前再聊一下" in prompt
    assert "- 晚上提醒我睡覺" in prompt
    assert "10-08 22:45 說了「要喝水喔」" in prompt and "沒開口" in prompt
    assert "分頁標題：影片網站" in prompt


def test_prompt_without_optional_parts():
    prompt = build_prompt(
        HeartbeatContext(
            datetime(2026, 10, 5, 9, 0, tzinfo=TAIPEI), 10, [], "", [], page_title=None
        )
    )

    assert "星期一" in prompt
    assert "最近的聊天：（沒有）" in prompt
    assert "（清單是空的）" in prompt
    assert "（這是第一次）" in prompt
    assert "分頁" not in prompt


def test_describe_duration():
    assert describe_duration(30) == "不到 1 分鐘"
    assert describe_duration(3600) == "約 1 小時"
    assert describe_duration(3600 + 5 * 60) == "約 1 小時 5 分鐘"
