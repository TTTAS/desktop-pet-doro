"""State management module."""

from .models import (
    MoveState,
    MoveStateCollection,
    State,
    StateChangeEvent,
    StateCollection,
    Transition,
    TransitionCollection,
    VisualConfig,
    normalize_state_key,
)
from .repository import (
    GifRepository,
    MoveStateRepository,
    StateListWriter,
    StateRepository,
    TransitionRepository,
)
from .service import StateService
from .state_parser import StateParser
from .request_commit import install_request_commit

install_request_commit(StateService)

__all__ = [
    "State",
    "MoveState",
    "Transition",
    "VisualConfig",
    "StateChangeEvent",
    "StateCollection",
    "MoveStateCollection",
    "TransitionCollection",
    "normalize_state_key",
    "StateRepository",
    "MoveStateRepository",
    "GifRepository",
    "TransitionRepository",
    "StateListWriter",
    "StateService",
    "StateParser",
]
