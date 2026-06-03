"""Cursor-free click port — fires UIA InvokePattern at a screen point.

Originally `AutomationManager` called `InputBackendPort.click_left` which
synthesised a real OS mouse event (pynput → SetCursorPos + mouse_event on
Windows). That design moves the user's cursor on every click — disruptive
when Doro is autonomously clicking targets the user isn't looking at.

This port is the cursor-static replacement. `try_invoke_at(x, y)` returns
True iff the UIA element under (x, y) exposes InvokePattern and the
Invoke() call succeeds; the manager surfaces False as
`ClickOutcome.NOT_INVOCABLE` and does not fall back to synthetic input.
"""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .service import A11yService


class A11yClickerPort(Protocol):
    def try_invoke_at(self, x: int, y: int) -> bool:
        """Return True iff the UIA element under (x, y) was successfully invoked."""


class A11yClickerAdapter:
    """Production adapter — delegates through `A11yService` to the UIA backend.

    Holds a reference to the live `A11yService` (rather than the backend
    directly) so the same gating that protects `read_foreground_tree`
    (``automation.a11y_enabled`` toggle, sensitive-app blacklist via the
    service's config layer) also applies to clicks. The constructor
    accepts `None` so callers can wire the production adapter
    unconditionally even when the a11y service didn't come up.
    """

    def __init__(self, a11y_service: "A11yService | None") -> None:
        self._a11y = a11y_service

    def try_invoke_at(self, x: int, y: int) -> bool:
        if self._a11y is None:
            return False
        return self._a11y.invoke_at_point(int(x), int(y))


class NullA11yClicker:
    """Always returns False. Wired on non-Windows where there is no UIA
    backend; the manager records NOT_INVOCABLE and the click is dropped
    instead of moving the cursor."""

    def try_invoke_at(self, x: int, y: int) -> bool:
        return False
