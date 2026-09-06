"""Action repository — persistent store for named actions (Phase 1c).

Stores ``ActionEntry`` records in ``actions.json`` alongside the other
schema files (``states.json``, ``move_states.json``, ``transitions.json``).

Ships two builtin actions — ``click`` (the wind-up before a
``[mouse:click]``) and ``dragged`` (played while the user drags Doro).
Future phases will allow user-added named actions; the schema reserves an
``is_builtin`` flag to differentiate.

Each entry carries a ``kind`` discriminator (``"click"`` / ``"dragged"``,
and later ``"move"`` / ``"transition"``). It is the seed of a unified
"action registry": the Action Manager iterates entries and groups them by
kind, so surfacing a new reaction is a data change, not a UI rewrite.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


CLICK_ACTION_KEY = "click"
DRAG_ACTION_KEY = "dragged"


@dataclass
class ActionEntry:
    """A single named action and its bound GIF (if any)."""

    key: str
    display_name: str
    gif_id: Optional[str] = None
    is_builtin: bool = False
    # Registry discriminator. Defaults to "click" so legacy actions.json
    # files (which only ever held the click builtin, without a kind field)
    # still load as the click action.
    kind: str = "click"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionEntry":
        return cls(
            key=data["key"],
            display_name=data.get("display_name", data["key"].title()),
            gif_id=data.get("gif_id"),
            is_builtin=bool(data.get("is_builtin", False)),
            kind=data.get("kind", "click"),
        )


class ActionRepository:
    """Read/write ``actions.json``.

    File schema::

        {
          "actions": [
            {"key": "click", "display_name": "Click", "gif_id": null, "is_builtin": true},
            ...
          ]
        }

    On first load the builtin ``click`` and ``dragged`` actions are
    auto-inserted with ``gif_id=None`` — the runtime fallback chain (see
    :class:`ActionService`) makes sure they still play without a bound
    asset.
    """

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._entries: dict[str, ActionEntry] = {}

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load(self) -> None:
        """Populate from disk, then ensure the builtins exist."""
        self._entries.clear()
        if self._file_path.is_file():
            try:
                raw = json.loads(self._file_path.read_text(encoding="utf-8"))
                for item in raw.get("actions", []):
                    entry = ActionEntry.from_dict(item)
                    self._entries[entry.key] = entry
            except Exception as exc:
                logger.warning(f"Failed to read {self._file_path}: {exc}")
        self._ensure_builtin(CLICK_ACTION_KEY, "Click", kind="click")
        self._ensure_builtin(DRAG_ACTION_KEY, "拖曳", kind="dragged")

    def _ensure_builtin(self, key: str, default_name: str, *, kind: str) -> None:
        """Insert a builtin action, or re-affirm its builtin flag/kind.

        A user's bound ``gif_id`` and renamed ``display_name`` survive; only
        the ``is_builtin`` flag and ``kind`` are re-asserted so an older
        actions.json (missing these) is upgraded in place on next save.
        """
        existing = self._entries.get(key)
        if existing is None:
            self._entries[key] = ActionEntry(
                key=key,
                display_name=default_name,
                gif_id=None,
                is_builtin=True,
                kind=kind,
            )
        else:
            self._entries[key] = ActionEntry(
                key=existing.key,
                display_name=existing.display_name or default_name,
                gif_id=existing.gif_id,
                is_builtin=True,
                kind=kind,
            )

    def save(self) -> bool:
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"actions": [e.to_dict() for e in self._entries.values()]}
            self._file_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.warning(f"Failed to write {self._file_path}: {exc}")
            return False

    # ─── Read API ──────────────────────────────────────────────────

    def get(self, key: str) -> Optional[ActionEntry]:
        return self._entries.get(key)

    def all_keys(self) -> list[str]:
        return list(self._entries.keys())

    def all_entries(self) -> list[ActionEntry]:
        return list(self._entries.values())

    # ─── Write API ─────────────────────────────────────────────────

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
