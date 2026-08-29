"""PR B request/commit helpers installed onto StateService.

Temporary: import-time install. Merge blocker is inlining these
methods into service.py and deleting this module.
"""

from __future__ import annotations

from typing import Optional

from ...utils.logger import get_logger
from .models import StateChangeEvent, normalize_state_key

logger = get_logger(__name__)


def install_request_commit(cls):
    """Patch *cls* (StateService) with request/commit behaviour."""
    if getattr(cls, "_request_commit_installed", False):
        return cls

    _orig_init = cls.__init__
    _orig_initialize = cls.initialize

    def __init__(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        self._requested_key: Optional[str] = None

    def initialize(self, default_gif_path=None) -> None:
        _orig_initialize(self, default_gif_path=default_gif_path)
        self._requested_key = self._states.current_key()

    def get_committed_state_key(self) -> Optional[str]:
        return self._states.current_key()

    def get_requested_state_key(self) -> Optional[str]:
        return self._requested_key

    def request_state(self, key: str, *, force: bool = False) -> bool:
        key = normalize_state_key(key)
        if self._states.get(key) is None:
            logger.warning(f"Failed to set state: '{key}' not found")
            return False

        if force:
            return self.commit_state(key, forced=True)

        self._release_expired_lock()
        if self._transition_coordinator.is_active():
            logger.warning(f"State change rejected: '{key}' (transition in progress)")
            self._requested_key = key
            return False

        return self.commit_state(key)

    def commit_state(self, key: str, *, forced: bool = False) -> bool:
        key = normalize_state_key(key)
        old_key = self._states.current_key()
        if not self._states.set_current(key):
            logger.warning(f"Failed to set state: '{key}' not found")
            return False

        self._requested_key = key
        logger.info(
            f"State changed: {old_key} -> {key}" + (" [forced]" if forced else "")
        )

        state = self._states.get(key)
        if self.on_state_changed and state:
            event = StateChangeEvent(old_key, key, state)
            self.on_state_changed(event)

        return True

    def set_state(self, key: str, *, force: bool = False) -> bool:
        return self.request_state(key, force=force)

    def _apply_pending_request(self) -> None:
        pending = self._requested_key
        committed = self._states.current_key()
        if pending is None or pending == committed:
            return
        logger.debug(f"Applying queued state request: {committed} -> {pending}")
        self.commit_state(pending)

    def _release_expired_lock(self) -> None:
        if self._transition_coordinator.expire_if_needed():
            self._apply_pending_request()

    def begin_transition(self) -> bool:
        self._release_expired_lock()
        return self._transition_coordinator.begin()

    def end_transition(self) -> bool:
        released = self._transition_coordinator.end()
        if released:
            self._apply_pending_request()
        else:
            self._release_expired_lock()
        return released

    def is_transitioning(self) -> bool:
        self._release_expired_lock()
        return self._transition_coordinator.is_active()

    cls.__init__ = __init__
    cls.initialize = initialize
    cls.get_committed_state_key = get_committed_state_key
    cls.get_requested_state_key = get_requested_state_key
    cls.request_state = request_state
    cls.commit_state = commit_state
    cls.set_state = set_state
    cls._apply_pending_request = _apply_pending_request
    cls._release_expired_lock = _release_expired_lock
    cls.begin_transition = begin_transition
    cls.end_transition = end_transition
    cls.is_transitioning = is_transitioning
    cls._request_commit_installed = True
    return cls
