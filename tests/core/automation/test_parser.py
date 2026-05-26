"""Tests for the mouse-bracket parser.

Phase 1c hard invariant: only the bare token `mouse:click` is accepted.
Every other shape — coordinates, alternate buttons, alternate actions —
must be rejected by the parser itself, not by a downstream check.
"""

from __future__ import annotations

import pytest

from doro_app.core.automation.parser import parse_mouse_bracket


class TestParserAcceptance:
    def test_bare_click_accepted(self):
        result = parse_mouse_bracket("mouse:click")
        assert result is not None
        assert result.accepted is True

    def test_whitespace_around_click_accepted(self):
        result = parse_mouse_bracket("  mouse : click  ")
        assert result is not None
        assert result.accepted is True

    def test_uppercase_click_accepted(self):
        result = parse_mouse_bracket("MOUSE:Click")
        assert result is not None
        assert result.accepted is True


class TestParserNonMouse:
    """Non-mouse brackets should yield None, not False-accepted."""

    @pytest.mark.parametrize("token", [
        "move:left",
        "MOVE:to;x=10;y=20",
        "state:happy",
        "",
        "   ",
        "click",  # missing 'mouse:' prefix
    ])
    def test_non_mouse_returns_none(self, token):
        assert parse_mouse_bracket(token) is None


class TestParserRejection:
    """Mouse brackets that we recognize but refuse to execute."""

    @pytest.mark.parametrize("token,reason_substring", [
        # Coordinate form — the core Phase 1c invariant. Permanently banned.
        ("mouse:click;x=100;y=200", "does not accept parameters"),
        ("mouse:click;x=1", "does not accept parameters"),
        ("mouse:click;y=1", "does not accept parameters"),
        # Alternate buttons.
        ("mouse:click;button=right", "does not accept parameters"),
        ("mouse:click;button=middle", "does not accept parameters"),
        # Alternate actions — none accepted in Phase 1c.
        ("mouse:double_click", "unsupported mouse action"),
        ("mouse:drag;dx=10;dy=10", "unsupported mouse action"),
        ("mouse:scroll;dy=120", "unsupported mouse action"),
        ("mouse:right_click", "unsupported mouse action"),
        # Missing action altogether.
        ("mouse", "missing action"),
    ])
    def test_rejected_with_reason(self, token, reason_substring):
        result = parse_mouse_bracket(token)
        assert result is not None
        assert result.accepted is False
        assert reason_substring in result.reason
