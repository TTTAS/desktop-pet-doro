"""Player wiring for Option A: skip stale transition_completed emit.

Does not play a real GIF. Calls _on_transition_complete after the clip
target and committed key have already diverged.
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from doro_app.core.state.transition_player import TransitionPlayer


def _ensure_qt_app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class _FakeService:
    def __init__(self, committed: str) -> None:
        self._committed = committed
        self.end_calls = 0

    def end_transition(self) -> bool:
        self.end_calls += 1
        return True

    def is_transitioning(self) -> bool:
        return False

    def get_committed_state_key(self) -> str:
        return self._committed

    def get_current_state_key(self) -> str:
        return self._committed

    def find_transition(self, *_args, **_kwargs):
        return None

    def get_transition_gif_path(self, *_args, **_kwargs):
        return None

    def begin_transition(self) -> bool:
        return True


def test_skips_emit_when_committed_moved_off_clip_target():
    _ensure_qt_app()
    service = _FakeService(committed="sad")
    player = TransitionPlayer(service)
    emitted: list[str] = []
    player.transition_completed.connect(emitted.append)

    player._is_playing = True
    player._target_state_key = "happy"
    player._on_transition_complete()

    assert emitted == []
    assert service.end_calls == 1
    assert player.is_playing is False


def test_emits_when_committed_still_matches_clip_target():
    _ensure_qt_app()
    service = _FakeService(committed="happy")
    player = TransitionPlayer(service)
    emitted: list[str] = []
    player.transition_completed.connect(emitted.append)

    player._is_playing = True
    player._target_state_key = "happy"
    player._on_transition_complete()

    assert emitted == ["happy"]
    assert service.end_calls == 1
