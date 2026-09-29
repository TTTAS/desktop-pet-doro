"""``parse_web_read_command`` 的單元測試（純邏輯，不需要瀏覽器）。"""

from __future__ import annotations

import pytest

from doro_app.core.web.intent import (
    is_affirmative,
    is_stop,
    parse_operate_command,
    parse_read_current_command,
    parse_web_read_command,
)


class TestParseWebReadCommand:
    def test_read_verb_plus_url_is_command(self):
        req = parse_web_read_command("幫我讀這頁 https://example.com/news")
        assert req is not None
        assert req.url == "https://example.com/news"

    def test_question_is_extracted_without_url(self):
        req = parse_web_read_command("幫我讀 https://example.com 這篇在講什麼")
        assert req is not None
        assert "https://example.com" not in req.question
        assert "這篇在講什麼" in req.question

    def test_summary_keyword_triggers(self):
        req = parse_web_read_command("摘要一下 http://a.test/page")
        assert req is not None
        assert req.url == "http://a.test/page"

    def test_english_read_keyword(self):
        req = parse_web_read_command("read https://example.org please")
        assert req is not None
        assert req.url == "https://example.org"

    def test_trailing_punctuation_not_part_of_url(self):
        req = parse_web_read_command("幫我讀這頁 https://example.com/文章。")
        assert req is not None
        assert req.url.endswith("/文章")
        assert "。" not in req.url

    # ── 不該被攔截的情況 ──────────────────────────────────────────

    def test_url_without_read_verb_is_not_command(self):
        # 只是貼了網址、沒有讀取動詞 → 交給正常聊天
        assert parse_web_read_command("這是我的部落格 https://example.com") is None

    def test_read_verb_without_url_is_not_command(self):
        # 有「讀」但沒有網址 → 不是讀網頁指令
        assert parse_web_read_command("幫我讀一下這本書") is None

    def test_casual_kan_without_url_is_not_command(self):
        # 「看」在閒聊裡很常見，沒有網址就不該誤判
        assert parse_web_read_command("你看我是不是很棒") is None

    def test_empty_or_blank(self):
        assert parse_web_read_command("") is None
        assert parse_web_read_command("   ") is None

    @pytest.mark.parametrize(
        "text",
        [
            "讀取 https://a.test",
            "看這頁 https://a.test",
            "打開這頁 https://a.test",
            "讀這個網頁 https://a.test",
        ],
    )
    def test_various_intents(self, text):
        assert parse_web_read_command(text) is not None


class TestParseOperateCommand:
    """操作只認明講（Q9=甲）。"""

    def test_operate_phrases_trigger(self):
        for text in [
            "幫我操作一下購物網站",
            "幫我在 pchome 搜尋 doro 週邊",
            "幫我點第一個結果",
            "幫我填一下這個表單",
            "去 google 幫我查天氣",
        ]:
            assert parse_operate_command(text) == text.strip()

    def test_plain_chat_not_operate(self):
        assert parse_operate_command("今天天氣真好") is None
        assert parse_operate_command("你在做什麼") is None

    def test_empty(self):
        assert parse_operate_command("") is None
        assert parse_operate_command("   ") is None


class TestParseReadCurrentCommand:
    """讀 doro 目前開著的那頁（無網址）。"""

    def test_referent_plus_intent(self):
        for text in [
            "讀你剛剛開的網頁",
            "這頁在說什麼",
            "幫我讀這頁",
            "這個網頁的重點是什麼",
            "唸一下目前這頁",
            "摘要這篇",
        ]:
            assert parse_read_current_command(text) == text.strip()

    def test_with_url_goes_to_normal_read(self):
        # 有網址 → 不歸 read_current（交給 parse_web_read_command）
        assert parse_read_current_command("幫我讀這頁 https://a.test") is None

    def test_plain_chat_not_matched(self):
        assert parse_read_current_command("今天天氣如何") is None
        assert parse_read_current_command("幫我操作一下") is None
        assert parse_read_current_command("") is None


class TestConfirmWords:
    def test_affirmative(self):
        for w in ["好", "好的", "可以", "是", "嗯", "行", "ok", "yes", "沒問題", "同意"]:
            assert is_affirmative(w) is True

    def test_not_affirmative(self):
        for w in ["不要", "不", "取消", "等等", "為什麼", ""]:
            assert is_affirmative(w) is False

    def test_stop(self):
        for w in ["停", "停下來", "取消", "算了", "stop", "abort"]:
            assert is_stop(w) is True

    def test_not_stop(self):
        assert is_stop("好啊繼續") is False
        assert is_stop("") is False
