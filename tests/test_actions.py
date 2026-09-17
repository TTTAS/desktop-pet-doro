"""Tests for doro_app.utils.actions inline move extraction."""

from __future__ import annotations

import pytest

from doro_app.utils.actions import extract_inline_move_commands, INLINE_MOVE_PATTERN


class TestInlineMovePattern:
    """INLINE_MOVE_PATTERN should match bare move commands in text."""

    @pytest.mark.parametrize(
        "text, expected_dir",
        [
            ("move left", "left"),
            ("walk right", "right"),
            ("go up", "up"),
            ("移動左", "左"),
            ("走右", "右"),
            ("向左", "左"),
            ("往右", "右"),
            ("move:left", "left"),
            ("move_right", "right"),
            ("mv left", "left"),
            ("step down", "down"),
            ("run left", "left"),
        ],
    )
    def test_matches_bare_commands(self, text: str, expected_dir: str):
        match = INLINE_MOVE_PATTERN.search(text)
        assert match is not None, f"Expected to match: {text!r}"
        assert match.group(1).strip() == expected_dir

    @pytest.mark.parametrize(
        "text",
        [
            "remove left",  # "remove" contains "move" but shouldn't match
            "improve right",  # "improve" contains "move" but shouldn't match
            "approved",  # "approved" contains partial keywords
        ],
    )
    def test_no_false_positives(self, text: str):
        match = INLINE_MOVE_PATTERN.search(text)
        assert match is None, f"Should NOT match: {text!r}"


class TestExtractInlineMoveCommands:
    """extract_inline_move_commands should strip move commands from text."""

    def test_single_command(self):
        cleaned, dirs = extract_inline_move_commands("你好 move left")
        assert dirs == ["left"]
        assert "move" not in cleaned.lower()
        assert "你好" in cleaned

    def test_chinese_command(self):
        cleaned, dirs = extract_inline_move_commands("嗨嗨 走左")
        assert dirs == ["左"]
        assert "走" not in cleaned

    def test_multiple_commands(self):
        cleaned, dirs = extract_inline_move_commands("move left 你好 walk right")
        assert len(dirs) == 2
        assert "left" in dirs
        assert "right" in dirs

    def test_no_commands(self):
        cleaned, dirs = extract_inline_move_commands("今天天氣真好")
        assert dirs == []
        assert cleaned == "今天天氣真好"

    def test_command_with_punctuation(self):
        cleaned, dirs = extract_inline_move_commands("move left，你好嗎")
        assert dirs == ["left"]
        assert "你好嗎" in cleaned

    def test_only_command(self):
        cleaned, dirs = extract_inline_move_commands("move right")
        assert dirs == ["right"]
        assert cleaned == ""

    def test_command_at_start_of_line(self):
        cleaned, dirs = extract_inline_move_commands("walk up\n你好")
        assert dirs == ["up"]
        assert "你好" in cleaned
