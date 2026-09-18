"""Phase 1d accessibility-tree reading.

Reads only the *foreground* window's interactable elements (button / link /
input / …) with their screen coordinates, so the LLM can translate "click
the bookmark button" into a `[move:to;x=;y=]` + `[mouse:click]` instead of
asking the user for coordinates. Gated behind `automation.a11y_enabled`
(independent of mouse clicking) and a sensitive-app blacklist. See
`/root/.claude/plans/velvet-pondering-ullman.md` for the full rationale.
"""

from .backend_null import NullA11yBackend
from .clicker import A11yClickerAdapter, A11yClickerPort, NullA11yClicker
from .fakes import FakeA11yBackend
from .models import A11yElement
from .port import A11yBackendPort
from .service import A11yService

__all__ = [
    "A11yBackendPort",
    "A11yClickerAdapter",
    "A11yClickerPort",
    "A11yElement",
    "A11yService",
    "FakeA11yBackend",
    "NullA11yBackend",
    "NullA11yClicker",
]
