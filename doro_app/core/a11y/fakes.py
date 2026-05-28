"""Test doubles for the a11y subsystem (Phase 1d).

Lets :class:`A11yService` be exercised without a real OS accessibility API
(none is installed on the dev/CI target). Tests drive the returned element
list and can simulate a hanging read via ``delay``.
"""

from __future__ import annotations

import time
from typing import Optional

from .models import A11yElement


class FakeA11yBackend:
    """In-memory :class:`A11yBackendPort` stand-in."""

    def __init__(
        self,
        elements: Optional[list[A11yElement]] = None,
        *,
        delay: float = 0.0,
        return_none: bool = False,
    ) -> None:
        self.elements = elements or []
        self.delay = delay
        self.return_none = return_none
        self.read_calls: list[int] = []

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        self.read_calls.append(int(handle))
        if self.delay:
            time.sleep(self.delay)
        if self.return_none:
            return None
        return list(self.elements)
