"""Decide whether a finished transition clip should load its original target.

Kept free of Qt so unit tests can import it without PySide6.
"""

from __future__ import annotations

from typing import Optional


def should_emit_completed_target(
    target_key: Optional[str],
    committed_key: Optional[str],
) -> bool:
    """True when the finished clip's target is still the committed state.

    If end_transition() applied a queued request, committed_key has moved
    on and emitting the stale target would load the wrong sprite.
    """
    return bool(target_key) and committed_key == target_key
