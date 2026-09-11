"""Validated page events and event-based reaction selection; no UI or networking."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class PageEvent:
    tab_id: int
    url: str
    title: str
    text: str

    @classmethod
    def from_message(cls, data: dict) -> PageEvent | None:
        if (
            data.get("type") != "page"
            or data.get("focused") is not True
            or data.get("visible") is not True
        ):
            return None
        if type(data.get("tab_id")) is not int or data["tab_id"] < 0:
            return None
        if not all(isinstance(data.get(k), str) for k in ("url", "title", "text")):
            return None
        try:
            url = urlsplit(data["url"])
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
            ):
                return None
        except ValueError:
            return None
        return cls(data["tab_id"], data["url"][:2048], data["title"][:200], data["text"][:6000])

    @property
    def fingerprint(self) -> str:
        content = re.sub(r"\s+", " ", self.title + "\n" + self.text).strip().casefold()
        return hashlib.sha256((self.url + "\n" + content).encode()).hexdigest()


class EventGate:
    """Coalesce while busy and remember attempted content, with no time quota.

    Exact normalized content is deduplicated locally. The model additionally
    compares the last reaction and chooses SILENT when a new event means the
    same thing. Memory capacity is a cache bound, not a speech/request limit.
    """

    def __init__(self):
        self.pending: PageEvent | None = None
        self._seen: dict[str, None] = {}
        self.degraded = False

    def offer(self, event: PageEvent | None) -> None:
        self.pending = (
            event if event and event.text.strip() and event.fingerprint not in self._seen else None
        )

    def take(self) -> PageEvent | None:
        event, self.pending = self.pending, None
        if event:
            self._seen[event.fingerprint] = None
            if len(self._seen) > 256:
                del self._seen[next(iter(self._seen))]
        return event

    def finish(self, success: bool) -> None:
        self.degraded = not success
