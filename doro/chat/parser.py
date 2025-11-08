import re
from typing import List, Tuple

ACTION_PATTERN = re.compile(r"\(([^()]+)\)")
BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def parse_actions_from_text(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Return cleaned text plus extracted action tokens."""
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


__all__ = ["ACTION_PATTERN", "BRACKET_PATTERN", "parse_actions_from_text"]
