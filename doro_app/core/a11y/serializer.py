"""Structured serialization of a11y elements: one JSON object per line.

Produces lines like::

    {"id":1,"role":"button","name":"書籤","box":[350,120,24,24]}
    {"id":2,"role":"input","name":"網址列","box":[140,75,800,36],"value":"https://example.com"}

``id`` is the element's 1-based position in the list handed to
:func:`serialize`; a click names that id and the program resolves it back
to coordinates, so the model never does pixel arithmetic.

The output is capped at ``A11Y_MAX_SERIALIZED_BYTES``; past the cap it
stops and appends a "還有 N 個元件未列出" marker so the prompt can't
balloon.
"""

from __future__ import annotations

import json

from ...constants import (
    A11Y_MAX_SERIALIZED_BYTES,
    A11Y_NAME_MAX_CHARS,
    A11Y_VALUE_MAX_CHARS,
)
from .models import A11yElement

# Reserve room so the truncation marker itself always fits under the cap.
_MARKER_RESERVE_BYTES = 80

# Control characters (C0 + DEL): U+0000–U+001F and U+007F. We strip
# these from element text so a malicious page can't smuggle newlines or
# escape sequences into the prompt block. C1 (U+0080–U+009F) is left
# alone — legitimate UTF-8 text never contains it as a control either.
_CONTROL_CHARS_TABLE = {c: " " for c in list(range(0x20)) + [0x7F]}


def _sanitize(text: str, max_chars: int) -> str:
    """Strip control chars, neutralise quotes, and cap to ``max_chars``.

    The serialized form puts text inside ``"…"`` for both ``name`` and
    ``value``; an embedded ``"`` would otherwise let an attacker close
    one field and inject a fake one. We replace it with the fullwidth
    quote ``”`` (U+201D) so the text is still human-readable but cannot
    terminate the syntactic quote pair.
    """
    if not text:
        return ""
    cleaned = text.translate(_CONTROL_CHARS_TABLE).replace('"', "”")
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def _format_element(element_id: int, el: A11yElement) -> str:
    item: dict = {
        "id": element_id,
        "role": el.role,
        "name": _sanitize(el.name, A11Y_NAME_MAX_CHARS),
        "box": [el.x, el.y, el.width, el.height],
    }
    if el.value:
        item["value"] = _sanitize(el.value, A11Y_VALUE_MAX_CHARS)
    return json.dumps(item, ensure_ascii=False, separators=(",", ":"))


def listed_count(body: str) -> int:
    """How many elements a serialized body actually lists (ids 1..n)."""
    return sum(1 for line in body.splitlines() if line.startswith("{"))


def serialize(elements: list[A11yElement], max_bytes: int = A11Y_MAX_SERIALIZED_BYTES) -> str:
    """Serialize elements to a compact block, truncating past ``max_bytes``."""
    if not elements:
        return ""

    budget = max(0, max_bytes - _MARKER_RESERVE_BYTES)
    lines: list[str] = []
    used = 0
    for index, el in enumerate(elements):
        line = _format_element(index + 1, el)
        cost = len(line.encode("utf-8")) + 1  # +1 for the newline
        if used + cost > budget and lines:
            remaining = len(elements) - index
            lines.append(f"... [還有 {remaining} 個元件未列出]")
            break
        lines.append(line)
        used += cost
    return "\n".join(lines)
