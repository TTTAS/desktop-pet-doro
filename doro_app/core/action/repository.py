"""Action repository — persistent store for named actions (Phase 1c).

Stores ``ActionEntry`` records in ``actions.json`` alongside the other
schema files (``states.json``, ``move_states.json``, ``transitions.json``).

Phase 1c only ships one builtin action — ``click``. Future phases (1e/1f)
will allow user-added named actions; the schema reserves an
``is_builtin`` flag to differentiate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ...utils.logger import get_logger

logger = get_logger(__name__)


CLICK_ACTION_KEY = "click"


@dataclass
class ActionEntry:
    """A single named action and its bound GIF (if any)."""

    key: str
    display_name: str
    gif_id: str | None = None
    is_builtin: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ActionEntry:
        return cls(
            key=data["key"],
            display_name=data.get("display_name", data["key"].title()),
            gif_id=data.get("gif_id"),
            is_builtin=bool(data.get("is_builtin", False)),
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

    On first load the builtin ``click`` action is auto-inserted with
    ``gif_id=None`` — the runtime fallback chain (see
    :class:`ActionService`) makes sure clicks still work without an asset.
    """

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._entries: dict[str, ActionEntry] = {}

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load(self) -> None:
        """Populate from disk, then ensure the ``click`` builtin exists."""
        self._entries.clear()
        if self._file_path.is_file():
            try:
                raw = json.loads(self._file_path.read_text(encoding="utf-8"))
                for item in raw.get("actions", []):
                    entry = ActionEntry.from_dict(item)
                    self._entries[entry.key] = entry
            except Exception as exc:
                logger.warning(f"Failed to read {self._file_path}: {exc}")
        self._ensure_click_builtin()

    def _ensure_click_builtin(self) -> None:
        if CLICK_ACTION_KEY not in self._entries:
            self._entries[CLICK_ACTION_KEY] = ActionEntry(
                key=CLICK_ACTION_KEY,
                display_name="Click",
                gif_id=None,
                is_builtin=True,
            )
        else:
            # Preserve user gif_id; just re-affirm the builtin flag.
            existing = self._entries[CLICK_ACTION_KEY]
            self._entries[CLICK_ACTION_KEY] = ActionEntry(
                key=existing.key,
                display_name=existing.display_name or "Click",
                gif_id=existing.gif_id,
                is_builtin=True,
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

    def get(self, key: str) -> ActionEntry | None:
        return self._entries.get(key)

    def all_keys(self) -> list[str]:
        return list(self._entries.keys())

    def all_entries(self) -> list[ActionEntry]:
        return list(self._entries.values())

    # ─── Write API ─────────────────────────────────────────────────

    def update_gif_id(self, key: str, gif_id: str | None) -> bool:
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
