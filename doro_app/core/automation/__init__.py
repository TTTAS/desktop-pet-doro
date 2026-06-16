"""Phase 1c automation — restricted synthetic mouse clicks.

The contract: Doro must visibly walk to the target before any click is fired.
The click lands where Doro stands when the wind-up timer expires — an
LLM-supplied coordinate can only influence the landing spot via a preceding
`[move:to]`, and a proximity guard falls back to the foot position whenever
the requested target is farther than Doro visibly reached.
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
