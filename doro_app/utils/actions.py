"""Utility helpers for parsing action and movement instructions."""

from __future__ import annotations

import re

ACTION_PATTERN = re.compile(r"\(([^()]+)\)")
BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")
ACTION_ALIASES: dict[str, str] = {
    "idle": "idle",
    "default": "idle",
    "sleep": "idle",
    "sleepy": "idle",
    "nap": "idle",
    "rest": "idle",
    "relax": "idle",
    "chill": "idle",
    "calm": "idle",
    "excited": "idle",
    "happy": "idle",
    "dance": "idle",
    "wave": "idle",
    "party": "idle",
}

MOVE_TOKEN_PATTERN = re.compile(
    r"^(?:move|mv|walk|go|travel|shift|step|run|向|往|移動|走|行)[\s:_-]*([a-z]+|[上下左右]{1,2})$",
    re.IGNORECASE,
)

# Inline variant: finds bare move commands embedded in dialogue text.
# Uses word boundary (\b) on the left and lookahead on the right to avoid
# matching partial words (e.g. "remove" should NOT match).
INLINE_MOVE_PATTERN = re.compile(
    r"(?:^|(?<=\s)|(?<=\n))(?:move|mv|walk|go|travel|shift|step|run|向|往|移動|走|行)[\s:_-]*([a-z]+|[上下左右]{1,2})(?=\s|$|[，。！？,\.!\?])",
    re.IGNORECASE | re.MULTILINE,
)
MOVE_DIRECTIONS: dict[str, tuple[int, int]] = {
    "left": (-1, 0),
    "l": (-1, 0),
    "west": (-1, 0),
    "right": (1, 0),
    "r": (1, 0),
    "east": (1, 0),
    "up": (0, -1),
    "u": (0, -1),
    "north": (0, -1),
    "down": (0, 1),
    "d": (0, 1),
    "south": (0, 1),
    "upleft": (-1, -1),
    "leftup": (-1, -1),
    "ul": (-1, -1),
    "up-left": (-1, -1),
    "left-up": (-1, -1),
    "upright": (1, -1),
    "rightup": (1, -1),
    "ur": (1, -1),
    "up-right": (1, -1),
    "right-up": (1, -1),
    "downleft": (-1, 1),
    "leftdown": (-1, 1),
    "dl": (-1, 1),
    "down-left": (-1, 1),
    "left-down": (-1, 1),
    "downright": (1, 1),
    "rightdown": (1, 1),
    "dr": (1, 1),
    "down-right": (1, 1),
    "right-down": (1, 1),
    "上": (0, -1),
    "下": (0, 1),
    "左": (-1, 0),
    "右": (1, 0),
    "上左": (-1, -1),
    "上右": (1, -1),
    "下左": (-1, 1),
    "下右": (1, 1),
    "左上": (-1, -1),
    "右上": (1, -1),
    "左下": (-1, 1),
    "右下": (1, 1),
}


def parse_actions_from_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove bracket/parenthesis control tokens and return cleaned text plus structured actions."""
    actions: list[tuple[str, str]] = []

    def _collect_paren(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        if token:
            actions.append(("paren", token))
        return ""

    cleaned = ACTION_PATTERN.sub(_collect_paren, text)

    def _collect_bracket(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        if token:
            actions.append(("bracket", token))
        return ""

    cleaned = BRACKET_PATTERN.sub(_collect_bracket, cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = cleaned.replace(" \n", "\n").replace("\n ", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), actions


def extract_inline_move_commands(text: str) -> tuple[str, list[str]]:
    """Find bare move commands in text that were not wrapped in brackets/parens.

    Returns the cleaned text (commands removed) and a list of direction strings
    extracted from the matches (e.g. ["left", "右"]).
    """
    directions: list[str] = []

    def _collect(match: re.Match[str]) -> str:
        directions.append(match.group(1).strip())
        return ""

    cleaned = INLINE_MOVE_PATTERN.sub(_collect, text)
    # Clean up extra whitespace left behind
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = cleaned.replace(" \n", "\n").replace("\n ", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), directions
