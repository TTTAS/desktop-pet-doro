"""Build a default runner. Qt-free besides whatever the ports do."""

from __future__ import annotations

from typing import Callable, Optional

from .catalog import ReactionCatalog
from .director import ReactionDirector
from .runner import ReactionRunner


def build_default_runner(
    *,
    request_state: Callable[..., bool],
    speak: Callable[[str], None],
    schedule: Callable[[int, Callable[[], None]], None],
    move: Optional[Callable[[str, float], None]] = None,
    current_key: Optional[Callable[[], Optional[str]]] = None,
) -> ReactionRunner:
    """Catalog with built-ins + a director wired to the given ports."""
    catalog = ReactionCatalog()
    catalog.register_defaults()
    director = ReactionDirector(
        request_state=request_state,
        speak=speak,
        schedule=schedule,
        move=move,
        current_key=current_key,
    )
    return ReactionRunner(catalog, director)
