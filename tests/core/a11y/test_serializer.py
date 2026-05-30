"""Tests for the compact a11y element serializer."""

from __future__ import annotations

from doro_app.core.a11y.models import A11yElement
from doro_app.core.a11y.serializer import serialize


def _el(role="button", name="書籤", x=350, y=120, w=24, h=24, value=None):
    return A11yElement(role=role, name=name, x=x, y=y, width=w, height=h, value=value)


def test_basic_format():
    line = serialize([_el()])
    assert line == 'button "書籤" (350,120 24x24)'


def test_input_with_value():
    el = _el(role="input", name="網址列", x=140, y=75, w=800, h=36, value="https://example.com")
    line = serialize([el])
    assert line == 'input "網址列" (140,75 800x36)  value="https://example.com"'


def test_multiple_elements_joined_by_newline():
    out = serialize([_el(name="a"), _el(name="b")])
    assert out.splitlines() == [
        'button "a" (350,120 24x24)',
        'button "b" (350,120 24x24)',
    ]


def test_empty_list_gives_empty_string():
    assert serialize([]) == ""


def test_truncation_appends_marker_and_stays_under_cap():
    # 200 elements far exceed a tiny cap; expect truncation + marker.
    elements = [_el(name=f"item-{i}") for i in range(200)]
    out = serialize(elements, max_bytes=300)

    assert len(out.encode("utf-8")) <= 300
    assert "個元件未列出" in out
    last_line = out.splitlines()[-1]
    assert last_line.startswith("... [還有 ")


def test_truncation_marker_counts_remaining_accurately():
    elements = [_el(name=f"item-{i}") for i in range(10)]
    out = serialize(elements, max_bytes=120)
    listed = [ln for ln in out.splitlines() if not ln.startswith("... [")]
    marker = out.splitlines()[-1]
    remaining = 10 - len(listed)
    assert f"還有 {remaining} 個元件未列出" in marker


def test_no_truncation_when_under_cap():
    out = serialize([_el()], max_bytes=4096)
    assert "未列出" not in out
