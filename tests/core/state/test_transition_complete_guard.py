"""Guard used by TransitionPlayer after end_transition().

Kept in a Qt-free helper so this test does not need PySide6.
"""

from doro_app.core.state.transition_complete import should_emit_completed_target


def test_emit_when_committed_still_matches_target():
    assert should_emit_completed_target("happy", "happy") is True


def test_skip_when_queued_request_moved_committed():
    assert should_emit_completed_target("happy", "sad") is False


def test_skip_when_target_missing():
    assert should_emit_completed_target(None, "happy") is False
    assert should_emit_completed_target("", "happy") is False
