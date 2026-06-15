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
        invoke_delay: float = 0.0,
        return_none: bool = False,
        invoke_succeeds: bool = True,
    ) -> None:
        self.elements = elements or []
        self.delay = delay
        self.invoke_delay = invoke_delay
        self.return_none = return_none
        self.invoke_succeeds = invoke_succeeds
        self.read_calls: list[int] = []
        self.invoke_calls: list[tuple[int, int]] = []
        # Parallel list — the hwnd the service forwarded for each call so
        # tests can assert UIA subtree scoping happened, without
        # disturbing the (x, y) tuple shape older assertions rely on.
        self.invoke_hwnds: list[Optional[int]] = []

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        self.read_calls.append(int(handle))
        if self.delay:
            time.sleep(self.delay)
        if self.return_none:
            return None
        return list(self.elements)

    def invoke_at_physical_point(
        self, x: int, y: int, hwnd: Optional[int] = None,
    ) -> bool:
        self.invoke_calls.append((int(x), int(y)))
        self.invoke_hwnds.append(hwnd)
        if self.invoke_delay:
            time.sleep(self.invoke_delay)
        return bool(self.invoke_succeeds)
