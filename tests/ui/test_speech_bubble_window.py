"""Speech bubble sizing and placement (pure functions, no window needed)."""

from PySide6 import QtCore, QtGui

from doro_app.ui.components.speech_bubble_window import (
    BUBBLE_GAP,
    BUBBLE_MAX_WIDTH,
    BUBBLE_MIN_WIDTH,
    BUBBLE_SCREEN_MARGIN,
    bubble_panel_size,
    place_bubble,
)

AREA = QtCore.QRect(0, 0, 1200, 800)


def _font():
    font = QtGui.QFont()
    font.setPointSizeF(12.0)
    font.setBold(True)
    return font


def test_short_line_gets_a_narrow_bubble():
    assert bubble_panel_size("好～", _font()).width() == BUBBLE_MIN_WIDTH


def test_long_line_is_capped_and_wraps():
    one_line = bubble_panel_size("短句", _font())
    long = bubble_panel_size("先忙你的事情，我在旁邊休息一下。" * 3, _font())
    assert long.width() == BUBBLE_MAX_WIDTH
    assert long.height() > one_line.height()


def test_width_follows_the_text_between_the_limits():
    medium = bubble_panel_size("我在這裡陪你喔", _font())
    assert BUBBLE_MIN_WIDTH < medium.width() < BUBBLE_MAX_WIDTH


def test_explicit_newlines_add_height():
    single = bubble_panel_size("第一行", _font())
    double = bubble_panel_size("第一行\n第二行", _font())
    assert double.height() > single.height()


def test_bubble_goes_above_by_default_and_centres_on_doro():
    body = QtCore.QRect(500, 600, 200, 180)
    panel, above = place_bubble(body, QtCore.QSize(200, 80), AREA)
    assert above
    assert panel.bottom() < body.top()
    assert panel.top() == body.top() - BUBBLE_GAP - 80
    assert panel.center().x() == body.center().x()


def test_bubble_flips_below_when_there_is_no_room_above():
    body = QtCore.QRect(500, 30, 200, 180)
    panel, above = place_bubble(body, QtCore.QSize(200, 80), AREA)
    assert not above
    assert panel.top() == body.bottom() + BUBBLE_GAP


def test_bubble_stays_inside_the_work_area_at_screen_edges():
    for body in (QtCore.QRect(-60, 600, 200, 180), QtCore.QRect(1100, 600, 200, 180)):
        panel, _ = place_bubble(body, QtCore.QSize(280, 80), AREA)
        assert AREA.adjusted(
            BUBBLE_SCREEN_MARGIN, BUBBLE_SCREEN_MARGIN, -BUBBLE_SCREEN_MARGIN, -BUBBLE_SCREEN_MARGIN
        ).contains(panel)


def test_negative_monitor_origin():
    area = QtCore.QRect(-1920, -120, 1920, 1040)
    body = QtCore.QRect(-1000, 700, 200, 200)
    panel, above = place_bubble(body, QtCore.QSize(200, 80), area)
    assert above and area.contains(panel)
