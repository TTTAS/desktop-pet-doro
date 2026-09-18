"""`web_actions`：解析 `[web:...]` 指令 + 安全分級（純邏輯）。"""

from __future__ import annotations

from doro_app.core.web.web_actions import (
    WebAction,
    needs_confirmation,
    parse_web_action,
)


class TestParseWebAction:
    def test_goto(self):
        a = parse_web_action("(思考) 去看看～ [web:goto;url=https://a.test]")
        assert a is not None
        assert a.verb == "goto"
        assert a.params["url"] == "https://a.test"

    def test_click_with_index(self):
        a = parse_web_action("[web:click;n=3]")
        assert a.verb == "click"
        assert a.index() == 3

    def test_type_with_text(self):
        a = parse_web_action("[web:type;n=1;text=你好世界]")
        assert a.verb == "type"
        assert a.index() == 1
        assert a.params["text"] == "你好世界"

    def test_press(self):
        assert parse_web_action("[web:press;key=Enter]").params["key"] == "Enter"

    def test_bare_verbs(self):
        assert parse_web_action("[web:back]").verb == "back"
        assert parse_web_action("[web:done]").verb == "done"

    def test_unknown_verb_is_none(self):
        assert parse_web_action("[web:explode;n=1]") is None

    def test_no_action(self):
        assert parse_web_action("(開心) 嘿嘿人好呀～") is None
        assert parse_web_action("") is None

    def test_index_invalid_returns_none(self):
        assert parse_web_action("[web:click;n=abc]").index() is None


class TestNeedsConfirmation:
    """送出類 / 不可逆動作才要先問使用者。"""

    def test_scroll_goto_type_back_done_are_safe(self):
        names: dict[int, str] = {0: "搜尋框"}
        for raw in [
            "[web:goto;url=https://a.test]",
            "[web:scroll;dir=down]",
            "[web:type;n=0;text=hi]",
            "[web:back]",
            "[web:done]",
        ]:
            assert needs_confirmation(parse_web_action(raw), names) is False

    def test_press_enter_requires_actual_search_focus(self):
        a = parse_web_action("[web:press;key=Enter]")
        assert needs_confirmation(a, {}, "https://www.bing.com/search 搜尋") is True
        assert needs_confirmation(a) is True
        assert (
            needs_confirmation(
                a, {}, "https://www.bing.com/search", [{"focused": True, "input_type": "search"}]
            )
            is False
        )

    def test_press_enter_on_sensitive_page_needs_confirm(self):
        # 結帳/付款/登入頁按 Enter → 要問
        a = parse_web_action("[web:press;key=Enter]")
        assert needs_confirmation(a, {}, "https://shop.com/checkout 結帳") is True
        assert needs_confirmation(a, {}, "https://x.com/login 登入") is True

    def test_press_other_key_safe(self):
        assert (
            needs_confirmation(parse_web_action("[web:press;key=Tab]"), {}, "https://x/checkout")
            is False
        )

    def test_click_submit_button_needs_confirm(self):
        names = {2: "送出訂單"}
        assert needs_confirmation(parse_web_action("[web:click;n=2]"), names) is True

    def test_click_plain_link_is_safe(self):
        names = {2: "下一頁"}
        assert needs_confirmation(parse_web_action("[web:click;n=2]"), names) is False

    def test_click_english_buy_needs_confirm(self):
        names = {5: "Buy now"}
        assert needs_confirmation(parse_web_action("[web:click;n=5]"), names) is True

    def test_click_unknown_index_needs_confirm(self):
        # 編號對不上目前畫面 → 保守起見先問
        assert needs_confirmation(parse_web_action("[web:click;n=99]"), {0: "x"}) is True

    def test_click_missing_index_needs_confirm(self):
        assert needs_confirmation(WebAction(verb="click", params={}), {}) is True
