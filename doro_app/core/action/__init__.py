"""Named-action schema (Phase 1c).

A "named action" is a non-movement, non-transition animation that Doro
plays at a single point in time — currently just ``click`` (the
wind-up before a ``[mouse:click]``), with future room for keyboard
actions and the like.

Public surface:
- :class:`ActionEntry` — schema for an action's metadata + bound GIF.
- :class:`ActionRepository` — persistent ``actions.json`` store.
- :class:`ActionService` — high-level: ensures the ``click`` builtin
  exists, registers a protected display state for it on the
  :class:`StateService`, resolves the GIF path with a fallback chain.

Companion class :class:`FakeActionRepository` lives in :mod:`.fakes`.
"""

from .repository import ActionEntry, ActionRepository
from .service import ActionService

__all__ = ["ActionEntry", "ActionRepository", "ActionService"]
