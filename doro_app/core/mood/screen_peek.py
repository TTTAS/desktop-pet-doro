"""Gate for the rare "comment on my screen" peek (proposal 7).

Pure timing/permission logic — no Qt, no I/O — so the policy that keeps the
one routinely-LLM path cheap is unit-testable. The app owns the actual
a11y read + LLM send; this only decides *whether* a peek may happen now.
"""

from __future__ import annotations

from ...constants import SCREEN_PEEK_MIN_INTERVAL_S


class ScreenPeekGate:
    """Rate-caps and permission-gates screen peeks."""

    def __init__(self, min_interval_s: float = SCREEN_PEEK_MIN_INTERVAL_S) -> None:
        self._min_interval = float(min_interval_s)
        self._last: float = float("-inf")

    def should_peek(
        self,
        now: float,
        *,
        enabled: bool,
        busy: bool,
        manual: bool = False,
    ) -> bool:
        """Decide whether a peek may fire now, consuming the rate budget if so.

        ``enabled`` is the a11y opt-in (a peek needs to read the screen, so it
        is meaningless without it — even a manual trigger). ``manual`` (the
        user explicitly asking) bypasses the rate cap but still respects the
        opt-in and the busy guard. Auto peeks additionally honour the
        min-interval since the last peek.
        """
        if not enabled or busy:
            return False
        if not manual and (now - self._last) < self._min_interval:
            return False
        self._last = now
        return True
