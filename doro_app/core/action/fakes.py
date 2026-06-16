"""In-memory fakes for ActionRepository (pytest)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .repository import CLICK_ACTION_KEY, ActionEntry


class FakeActionRepository:
    """Stand-in for :class:`ActionRepository` that holds state in memory.

    Mirrors the read/write API used by :class:`ActionService` so the same
    service code paths are exercised in tests without touching the
    filesystem.
    """

    def __init__(self, entries: Optional[list[ActionEntry]] = None) -> None:
        self._entries: dict[str, ActionEntry] = {}
        for entry in entries or []:
            self._entries[entry.key] = entry
        self.save_calls: int = 0

    @property
    def file_path(self) -> Path:
        return Path("(in-memory FakeActionRepository)")

    def load(self) -> None:
        if CLICK_ACTION_KEY not in self._entries:
            self._entries[CLICK_ACTION_KEY] = ActionEntry(
                key=CLICK_ACTION_KEY,
                display_name="Click",
                gif_id=None,
                is_builtin=True,
            )

    def save(self) -> bool:
        self.save_calls += 1
        return True

    def get(self, key: str) -> Optional[ActionEntry]:
        return self._entries.get(key)

    def all_keys(self) -> list[str]:
        return list(self._entries.keys())

    def all_entries(self) -> list[ActionEntry]:
        return list(self._entries.values())

    def update_gif_id(self, key: str, gif_id: Optional[str]) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        self._entries[key] = ActionEntry(
            key=entry.key,
            display_name=entry.display_name,
            gif_id=gif_id,
            is_builtin=entry.is_builtin,
        )
        return self.save()
