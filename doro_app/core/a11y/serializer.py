"""Compact text serialization of a11y elements (Phase 1d).

Produces lines like::

    #0 button "書籤" (350,120 24x24)
    #1 input "網址列" (140,75 800x36)  value="https://example.com"

The leading ``#N`` is the element's index so the LLM can click it by id
(``[move:to;id=N]``) instead of computing pixel coordinates. The output is
capped
at ``A11Y_MAX_SERIALIZED_BYTES``; past the cap it stops and appends a
"還有 N 個元件未列出" marker so the prompt can't balloon.
"""

from __future__ import annotations

from .models import A11yElement
from ...constants import A11Y_MAX_SERIALIZED_BYTES

# Reserve room so the truncation marker itself always fits under the cap.
_MARKER_RESERVE_BYTES = 80


def _format_element(el: A11yElement) -> str:
    line = f'{el.role} "{el.name}" ({el.x},{el.y} {el.width}x{el.height})'
    if el.value:
        line += f'  value="{el.value}"'
    return line


def serialize(elements: list[A11yElement], max_bytes: int = A11Y_MAX_SERIALIZED_BYTES) -> str:
    """Serialize elements to a compact block, truncating past ``max_bytes``."""
    if not elements:
        return ""

    budget = max(0, max_bytes - _MARKER_RESERVE_BYTES)
    lines: list[str] = []
    used = 0
    for index, el in enumerate(elements):
        line = f"#{index} {_format_element(el)}"
        cost = len(line.encode("utf-8")) + 1  # +1 for the newline
        if used + cost > budget and lines:
            remaining = len(elements) - index
            lines.append(f"... [還有 {remaining} 個元件未列出]")
            break
        lines.append(line)
        used += cost
    return "\n".join(lines)
