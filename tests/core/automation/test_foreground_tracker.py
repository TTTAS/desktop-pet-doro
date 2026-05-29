"""Tests for the foreground-window tracker (last external window)."""

from __future__ import annotations

from doro_app.core.automation.foreground_tracker import (
    ForegroundTracker,
    next_external_handle,
)

OWN_PID = 4321


def test_external_window_replaces_previous():
    assert next_external_handle(handle=100, pid=9, own_pid=OWN_PID, previous=None) == 100
    assert next_external_handle(handle=200, pid=9, own_pid=OWN_PID, previous=100) == 200


def test_own_window_keeps_previous():
    # Doro's own window must never overwrite the last external handle.
    assert next_external_handle(handle=999, pid=OWN_PID, own_pid=OWN_PID, previous=100) == 100


def test_missing_handle_keeps_previous():
    assert next_external_handle(handle=None, pid=None, own_pid=OWN_PID, previous=100) == 100


def test_missing_pid_keeps_previous():
    assert next_external_handle(handle=300, pid=None, own_pid=OWN_PID, previous=100) == 100


def test_sample_updates_handle(qtbot):
    foreground = {"handle": 111, "pid": 9}
    tracker = ForegroundTracker(
        OWN_PID,
        handle_provider=lambda: foreground["handle"],
        pid_provider=lambda h: foreground["pid"],
    )

    tracker._sample()
    assert tracker.handle() == 111

    # Switching focus to Doro's own window keeps the last external handle.
    foreground.update(handle=222, pid=OWN_PID)
    tracker._sample()
    assert tracker.handle() == 111

    # A new external window updates it.
    foreground.update(handle=333, pid=42)
    tracker._sample()
    assert tracker.handle() == 333
