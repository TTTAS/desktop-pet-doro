"""Tests for a11y element filtering and redaction."""

from __future__ import annotations

from doro_app.core.a11y.filters import (
    REDACTED_VALUE,
    filter_elements,
    is_blacklisted,
)
from doro_app.core.a11y.models import A11yElement


def _el(role, name="x", value=None, is_password=False):
    return A11yElement(
        role=role, name=name, x=0, y=0, width=10, height=10,
        value=value, is_password=is_password,
    )


class TestFilterElements:
    def test_drops_non_interactable_roles(self):
        elements = [_el("button"), _el("pane"), _el("text"), _el("link")]
        kept = filter_elements(elements)
        assert [e.role for e in kept] == ["button", "link"]

    def test_keeps_all_interactable_roles(self):
        roles = ["button", "link", "input", "menuitem", "combobox", "checkbox", "radiobutton", "tab"]
        kept = filter_elements([_el(r) for r in roles])
        assert {e.role for e in kept} == set(roles)

    def test_masks_password_value(self):
        el = _el("input", name="password", value="hunter2", is_password=True)
        kept = filter_elements([el])
        assert len(kept) == 1
        assert kept[0].value == REDACTED_VALUE
        assert kept[0].is_password is True

    def test_preserves_non_password_value(self):
        el = _el("input", name="url", value="https://example.com")
        kept = filter_elements([el])
        assert kept[0].value == "https://example.com"

    def test_empty_input_gives_empty_output(self):
        assert filter_elements([]) == []


class TestIsBlacklisted:
    def test_substring_match_case_insensitive(self):
        assert is_blacklisted("Qt.KeePassXC.Window", ("KeePass",)) is True
        assert is_blacklisted("keepassxc", ("KeePass",)) is True

    def test_no_match(self):
        assert is_blacklisted("ChromeWidgetWin", ("KeePass", "Bitwarden")) is False

    def test_none_or_empty_class_is_not_blacklisted(self):
        assert is_blacklisted(None, ("KeePass",)) is False
        assert is_blacklisted("", ("KeePass",)) is False
        assert is_blacklisted("   ", ("KeePass",)) is False

    def test_empty_blacklist_blocks_nothing(self):
        assert is_blacklisted("KeePassXC", ()) is False
