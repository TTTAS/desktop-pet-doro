"""Tests for the idle-speech decision (canned vs LLM)."""

from doro_app.core.mood.idle_speech import (
    IdleAction,
    choose_idle_utterance,
)


def test_high_roll_with_canned_line_says_it():
    # roll (0.9) above the LLM chance (0.25) -> use the free pre-written line.
    u = choose_idle_utterance(
        roll=0.9,
        llm_chance=0.25,
        canned_line="人～doro好無聊喔……",
        has_llm_seed=True,
    )
    assert u.action is IdleAction.SAY_CANNED
    assert u.line == "人～doro好無聊喔……"


def test_low_roll_with_llm_seed_asks_llm():
    # roll (0.1) below the chance (0.25) -> spend the occasional LLM call.
    u = choose_idle_utterance(
        roll=0.1,
        llm_chance=0.25,
        canned_line="人～doro好無聊喔……",
        has_llm_seed=True,
    )
    assert u.action is IdleAction.ASK_LLM


def test_low_roll_without_llm_seed_falls_back_to_canned():
    # rolled for LLM but there's no LLM seed available -> still say the line
    # rather than going silent.
    u = choose_idle_utterance(
        roll=0.1,
        llm_chance=0.25,
        canned_line="人～摸摸doro嘛～",
        has_llm_seed=False,
    )
    assert u.action is IdleAction.SAY_CANNED
    assert u.line == "人～摸摸doro嘛～"


def test_nothing_to_say_moves():
    # Guard (green on arrival): no line and no LLM seed -> move instead.
    u = choose_idle_utterance(
        roll=0.9,
        llm_chance=0.25,
        canned_line=None,
        has_llm_seed=False,
    )
    assert u.action is IdleAction.MOVE
