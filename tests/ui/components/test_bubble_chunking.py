"""Tests for BubbleController's "speak in chunks" behaviour.

Long replies (web summaries, verify results) are split into several short
bubbles shown one after another so a single bubble never grows tall enough to
push the sprite up or run off the screen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from doro_app.constants import BUBBLE_CHUNK_MAX_CHARS
from doro_app.ui.components.bubble_controller import BubbleController

# --------------------------------------------------------------------------- #
# Pure splitting logic (no Qt needed — static methods)
# --------------------------------------------------------------------------- #


def test_short_text_stays_one_chunk():
    text = "嘿嘿，doro幫人去查查看喔～"
    assert BubbleController._split_into_chunks(text) == [text]


def test_long_text_splits_into_multiple_chunks():
    text = "。".join(f"這是第{i}個句子的內容都不算太短喔" for i in range(1, 12))
    chunks = BubbleController._split_into_chunks(text)
    assert len(chunks) > 1


def test_no_chunk_exceeds_max():
    text = "。".join(f"句子{i}拿來把整段文字撐得很長很長很長很長" for i in range(1, 20))
    chunks = BubbleController._split_into_chunks(text)
    assert all(len(c) <= BUBBLE_CHUNK_MAX_CHARS for c in chunks)


def test_single_oversized_sentence_is_hard_wrapped():
    # One "sentence" with no punctuation, longer than the limit.
    text = "字" * (BUBBLE_CHUNK_MAX_CHARS * 2 + 5)
    chunks = BubbleController._split_into_chunks(text)
    assert len(chunks) >= 3
    assert all(len(c) <= BUBBLE_CHUNK_MAX_CHARS for c in chunks)
    # No characters lost.
    assert "".join(chunks) == text


def test_chunks_preserve_all_characters_for_punctuated_text():
    text = "第一句。第二句！第三句？" * 8
    chunks = BubbleController._split_into_chunks(text)
    # Rejoining (punctuation kept with its sentence) reconstructs the stripped text.
    assert "".join(chunks) == text


def test_reading_delay_scales_and_is_bounded():
    from doro_app.constants import (
        BUBBLE_CHUNK_MAX_READ_MS,
        BUBBLE_CHUNK_MIN_READ_MS,
    )

    short = BubbleController._reading_delay_ms("短")
    long = BubbleController._reading_delay_ms("字" * 500)
    assert BUBBLE_CHUNK_MIN_READ_MS <= short <= BUBBLE_CHUNK_MAX_READ_MS
    assert long == BUBBLE_CHUNK_MAX_READ_MS
    assert long >= short


# --------------------------------------------------------------------------- #
# Behaviour (needs a QApplication for QTimer — provided by pytest-qt `qapp`)
# --------------------------------------------------------------------------- #


@pytest.fixture
def controller(qapp):
    return BubbleController(MagicMock())


def test_set_text_shows_first_chunk_and_queues_rest(controller):
    emitted: list[str] = []
    controller.text_changed.connect(lambda text, _override: emitted.append(text))

    long = "。".join(f"這是一個內容不算短的句子第{i}段" for i in range(1, 12))
    controller.set_text(long)

    expected = BubbleController._split_into_chunks(long)
    assert len(expected) > 1
    # First chunk shown immediately; the remainder waits in the queue.
    assert controller.text == expected[0]
    assert emitted[-1] == expected[0]
    assert controller._chunk_queue == expected[1:]


def test_advancing_walks_through_every_chunk(controller):
    long = "。".join(f"內容不算短的第{i}句話喔喔喔" for i in range(1, 12))
    controller.set_text(long)
    expected = BubbleController._split_into_chunks(long)

    seen = [controller.text]
    # Manually fire the advance handler until the queue drains.
    while controller._chunk_queue:
        controller._on_hide_timer_timeout()
        seen.append(controller.text)

    assert seen == expected


def test_new_message_cancels_pending_chunks(controller):
    long = "。".join(f"舊訊息的第{i}句話撐長一點" for i in range(1, 12))
    controller.set_text(long)
    assert controller._chunk_queue  # sequence in progress

    controller.set_text("新訊息一句話")
    assert controller._chunk_queue == []
    assert controller.text == "新訊息一句話"


def test_clear_text_drops_pending_chunks(controller):
    long = "。".join(f"要被清掉的第{i}句話撐長一點" for i in range(1, 12))
    controller.set_text(long)
    assert controller._chunk_queue

    controller.clear_text()
    assert controller._chunk_queue == []
    assert controller.text == ""
