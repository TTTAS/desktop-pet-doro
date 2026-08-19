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

from .click_action import CLICK_FAILED_STATE_KEY, make_click_action
from .dispatcher import Action, ActionDispatcher
from .movement_action import make_movement_action
from .phases import EffectPhase, Phase, VisualPhase, WaitPhase
from .repository import ActionEntry, ActionRepository
from .service import ActionService
from .walk_and_speak_action import make_walk_and_speak_action

__all__ = [
    "Action",
    "ActionDispatcher",
    "ActionEntry",
    "ActionRepository",
    "ActionService",
    "CLICK_FAILED_STATE_KEY",
    "EffectPhase",
    "Phase",
    "VisualPhase",
    "WaitPhase",
    "make_click_action",
    "make_movement_action",
    "make_walk_and_speak_action",
]
