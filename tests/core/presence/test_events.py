from doro_app.core.presence.models import EventGate, PageEvent


def message(**changes):
    return dict(
        {
            "type": "page",
            "focused": True,
            "visible": True,
            "tab_id": 2,
            "url": "https://example.test/a",
            "title": "Example",
            "text": "Hello world",
        },
        **changes,
    )


def test_only_focused_visible_http_pages():
    assert PageEvent.from_message(message())
    for change in (
        {"focused": False},
        {"visible": False},
        {"focused": "true"},
        {"url": "chrome://settings"},
        {"url": "https://user:secret@example.test"},
        {"tab_id": True},
        {"text": None},
    ):
        assert PageEvent.from_message(message(**change)) is None


def test_busy_events_coalesce_to_latest_and_deduplicate_whitespace():
    gate = EventGate()
    a = PageEvent.from_message(message(text="first"))
    b = PageEvent.from_message(message(text="second"))
    gate.offer(a)
    gate.offer(b)
    assert gate.take() == b
    gate.offer(PageEvent.from_message(message(text=" second  ")))
    assert gate.take() is None
    gate.offer(a)
    assert gate.take() == a


def test_failure_degrades_but_next_event_can_recover():
    gate = EventGate()
    gate.offer(PageEvent.from_message(message()))
    gate.take()
    gate.finish(False)
    assert gate.degraded
    gate.offer(PageEvent.from_message(message(text="new fact")))
    assert gate.take()
    gate.finish(True)
    assert not gate.degraded


def test_background_clear_drops_pending_page():
    gate = EventGate()
    gate.offer(PageEvent.from_message(message()))
    gate.offer(None)
    assert gate.take() is None
