"""Phase 1c automation — restricted synthetic mouse clicks.

The contract: Doro must visibly walk to the target before any click is fired.
The click coordinate is *always* Doro's current foot position at the moment
the wind-up timer expires — never a coordinate supplied by the LLM. See
`/root/.claude/plans/velvet-pondering-ullman.md` for the full rationale.
"""

from .manager import AutomationManager, ClickOutcome
from .parser import parse_mouse_bracket
from .port import InputBackendPort, AutomationWindowPort
from .fakes import FakeInputBackend, FakeAutomationWindow

__all__ = [
    "AutomationManager",
    "ClickOutcome",
    "parse_mouse_bracket",
    "InputBackendPort",
    "AutomationWindowPort",
    "FakeInputBackend",
    "FakeAutomationWindow",
]
