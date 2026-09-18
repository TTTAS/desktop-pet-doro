"""`ListenerRegistry` — a tiny subscribe / unsubscribe / emit helper.

Both `AutomationManager` (terminal click outcomes) and `MovementManager`
(movement completion) needed the same fire-and-forget listener pattern:
register a callback, hand back an unsubscribe handle, and later notify
every listener over a *snapshot* of the list so a listener may detach
itself mid-notification (the one-shot wait pattern that `WaitPhase`
relies on). Each manager had grown its own copy; this is the single
home for it.

Composition, not inheritance: a class *holds* a registry (or several)
rather than being one. This keeps the manager's own interface free of
listener plumbing and lets the registry be unit-tested on its own.

Listener exceptions are swallowed (and logged) — one misbehaving
subscriber must not stop the others from being notified, and the emitter
(a manager finalizing a click or movement) must not unwind because a
downstream waiter raised.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from ..utils.logger import get_logger

logger = get_logger(__name__)


# The listener callable's signature. Registries carry different payloads
# (`()` for movement completion, `(outcome, detail)` for click outcomes),
# so this is intentionally left as a broad `Callable[..., None]`.
_Listener = TypeVar("_Listener", bound=Callable[..., None])


class ListenerRegistry(Generic[_Listener]):
    """Holds a set of listeners and notifies them on `emit`.

    Usage::

        self._on_done: ListenerRegistry = ListenerRegistry()
        unsub = self._on_done.subscribe(callback)   # register
        ...
        self._on_done.emit(outcome, detail)         # notify all
    """

    def __init__(self, name: str = "listener") -> None:
        # `name` only labels the log line emitted when a listener raises,
        # so a mixed log still says *which* registry (e.g. "click-outcome"
        # vs "movement-completion") the failing callback belonged to.
        self._name = name
        self._listeners: list[_Listener] = []

    def subscribe(self, callback: _Listener) -> Callable[[], None]:
        """Register *callback* and return an idempotent unsubscribe handle.

        Listeners persist across `emit` calls until they unsubscribe — the
        typical one-shot waiter subscribes, then unsubscribes from inside
        its own callback on the first fire.
        """
        self._listeners.append(callback)

        def _unsubscribe() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return _unsubscribe

    def emit(self, *args: object) -> None:
        """Notify every current listener with *args*.

        Iterates over a snapshot so a listener can safely unsubscribe (or
        another can subscribe) during notification. A listener that raises
        is logged and skipped — it never blocks the remaining listeners.
        """
        for listener in list(self._listeners):
            try:
                listener(*args)
            except Exception:  # pragma: no cover - listeners should not raise
                logger.exception("%s listener raised during emit", self._name)
