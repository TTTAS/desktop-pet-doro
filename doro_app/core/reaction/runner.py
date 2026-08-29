"""Catalog + director facade. Qt-free."""

from __future__ import annotations

from typing import Optional

from .catalog import ReactionCatalog
from .director import ReactionDirector


class ReactionRunner:
    """Play a registered timeline by name.

    CoreManager / DoroApp hold one of these. The director still owns
    preemption and wait generation; this object only does the lookup.
    """

    def __init__(self, catalog: ReactionCatalog, director: ReactionDirector) -> None:
        self._catalog = catalog
        self._director = director

    def play(self, name: str) -> bool:
        """Start the named timeline. Unknown names return False."""
        timeline = self._catalog.get(name)
        if timeline is None:
            return False
        return self._director.play(timeline)

    def cancel(self) -> None:
        self._director.cancel()

    @property
    def is_playing(self) -> bool:
        return self._director.is_playing

    @property
    def current_name(self) -> Optional[str]:
        return self._director.current_name

    @property
    def catalog(self) -> ReactionCatalog:
        return self._catalog

    @property
    def director(self) -> ReactionDirector:
        return self._director
