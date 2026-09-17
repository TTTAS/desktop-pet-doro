"""`WebOperator` 的循環邏輯測試（全部用假物件，不開瀏覽器、不呼叫 AI）。"""

from __future__ import annotations

from doro_app.core.web.operator import (
    WebOperator,
    looks_like_captcha,
    looks_like_login_wall,
)
from doro_app.core.web.session import PageView


class FakeSession:
    def __init__(self, views, *, open_err=None, exec_err=None):
        self._views = list(views)
        self.open_err = open_err
        self.exec_err = exec_err
        self.executed = []
        self.opened = False

    def ensure_open(self):
        self.opened = True
        return self.open_err

    def snapshot(self):
        if len(self._views) > 1:
            return self._views.pop(0)
        return self._views[0]

    def execute(self, action):
        self.executed.append(action)
        return self.exec_err


class FakeLLM:
    def __init__(self, replies):
        self._replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self._replies.pop(0) if self._replies else "(狀態) 好了～ [web:done]"


def _view(elements=None, text="頁面內容"):
    return PageView(url="https://a.test", title="標題", text=text, elements=elements or [])


def test_safe_action_then_done():
    session = FakeSession([_view()])
    llm = FakeLLM(["[web:scroll;dir=down]", "(高興) 看完囉～ [web:done]"])
    confirms, emits = [], []
    op = WebOperator(session, llm, lambda d: confirms.append(d) or True, emits.append)

    op.run("看看這頁")

    assert len(session.executed) == 1
    assert session.executed[0].verb == "scroll"
    assert confirms == []  # 安全動作不問
    assert emits[-1] == "看完囉～"


def test_commit_action_asks_and_proceeds_on_yes():
    elements = [{"idx": 0, "tag": "button", "name": "送出訂單"}]
    session = FakeSession([_view(elements)])
    llm = FakeLLM(["[web:click;n=0]", "(高興) 送出好囉～ [web:done]"])
    confirms = []
    op = WebOperator(session, llm, lambda d: confirms.append(d) or True, lambda t: None)

    op.run("幫我送出")

    assert len(confirms) == 1
    assert "送出訂單" in confirms[0]
    assert session.executed[0].verb == "click"


def test_commit_action_aborts_on_no():
    elements = [{"idx": 0, "tag": "button", "name": "購買"}]
    session = FakeSession([_view(elements)])
    llm = FakeLLM(["[web:click;n=0]"])
    emits = []
    op = WebOperator(session, llm, lambda d: False, emits.append)

    op.run("幫我買")

    assert session.executed == []  # 使用者說不 → 不執行
    assert "不動" in emits[-1] or "不做" in emits[-1]


def test_ensure_open_error_stops_early():
    session = FakeSession([_view()], open_err="沒裝瀏覽器")
    llm = FakeLLM(["[web:scroll;dir=down]"])
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append)

    op.run("做事")

    assert emits == ["沒裝瀏覽器"]
    assert llm.prompts == []  # 沒開成功就不會問 AI


def test_snapshot_error_stops():
    session = FakeSession([PageView(error="讀不到頁面")])
    llm = FakeLLM(["[web:done]"])
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append)

    op.run("做事")

    assert emits == ["讀不到頁面"]


def test_max_steps_cap():
    session = FakeSession([_view()])
    # 一直給安全動作、永遠不 done
    llm = FakeLLM(["[web:scroll;dir=down]"] * 50)
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append, max_steps=5)

    op.run("無限捲")

    assert len(session.executed) == 5
    assert "停下來" in emits[-1]


def test_cancel_stops_between_steps():
    session = FakeSession([_view()])
    llm = FakeLLM(["[web:scroll;dir=down]"] * 50)
    emits = []
    # Cancellation is state, not a counter of how often safety is checked.
    def should_cancel():
        return len(session.executed) >= 1

    op = WebOperator(session, llm, lambda d: True, emits.append, should_cancel=should_cancel)
    op.run("一直捲")

    assert len(session.executed) == 1  # 只做了一步就被喊停
    assert "停下來" in emits[-1]


def test_bare_url_treated_as_goto():
    session = FakeSession([_view()])
    # 模型忘了包 [web:goto]，只丟網址；下一步就收工
    llm = FakeLLM(["我先去 https://www.google.com/search?q=doro 看看",
                   "(高) 找到了～ [web:done]"])
    op = WebOperator(session, llm, lambda d: True, lambda t: None)
    op.run("搜尋 doro")
    assert len(session.executed) == 1
    assert session.executed[0].verb == "goto"
    assert "google.com/search" in session.executed[0].params["url"]


def test_captcha_detection():
    assert looks_like_captcha(PageView(title="reCAPTCHA challenge")) is True
    assert looks_like_captcha(PageView(text="請完成驗證後繼續")) is True
    assert looks_like_captcha(PageView(url="https://www.google.com/sorry/index")) is True
    assert looks_like_captcha(PageView(title="搜尋結果", text="doro 週邊商品")) is False


def test_captcha_pauses_and_asks_user():
    # 碰到驗證 → 暫停問使用者（不亂點、不問 AI）
    session = FakeSession([_view(text="請完成人機驗證，我不是機器人")])
    llm = FakeLLM(["[web:click;n=0]"] * 5)
    confirms, emits = [], []
    # 使用者回「不要」→ 放棄
    op = WebOperator(session, llm, lambda d: (confirms.append(d), False)[1], emits.append)
    op.run("幫我搜尋")
    assert session.executed == []
    assert llm.prompts == []
    assert confirms and "驗證" in confirms[0]
    assert "不做" in emits[-1]


def test_captcha_resume_after_user_handles():
    # 驗證頁 → 使用者說「好」（已處理）→ 下一輪看到乾淨頁 → 接著做
    captcha = PageView(url="https://x", title="reCAPTCHA", text="verify", elements=[])
    clean = _view(elements=[{"idx": 0, "tag": "a", "name": "連結"}])
    session = FakeSession([captcha, clean])
    llm = FakeLLM(["[web:scroll;dir=down]", "(高) 好了～ [web:done]"])
    confirms = []
    op = WebOperator(session, llm, lambda d: (confirms.append(d), True)[1], lambda t: None)
    op.run("測試")
    assert confirms                                    # 有暫停問使用者
    assert [a.verb for a in session.executed] == ["scroll"]  # 過驗證後有繼續做


def test_repeated_same_page_goto_stops():
    # 模型一直叫 doro 開「已經在的同一頁」→ 提醒數次仍不聽 → 停手
    session = FakeSession([_view()])  # view.url = https://a.test
    llm = FakeLLM(["[web:goto;url=https://a.test]"] * 10)
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append)
    op.run("打轉測試")
    assert session.executed == []          # 重複動作根本沒執行
    assert "卡" in emits[-1] or "停" in emits[-1]


def test_self_recovers_from_repeat_after_nudge():
    # 先重複一次（會被提醒、不執行），模型接著換動作 → doro 自己脫困、不放棄
    elements = [{"idx": 0, "tag": "a", "name": "下一頁"}]
    session = FakeSession([_view(elements)])  # url=https://a.test
    llm = FakeLLM([
        "[web:goto;url=https://a.test]",   # 重複目前頁 → 提醒、跳過
        "[web:click;n=0]",                  # 換了動作 → 執行
        "(高) 好了～ [web:done]",
    ])
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append)
    op.run("脫困測試")
    assert [a.verb for a in session.executed] == ["click"]  # 只執行了換過的動作
    assert emits[-1] == "好了～"                              # 正常收尾、沒放棄


def test_bare_url_same_as_current_not_reopened():
    # 模型只是聊天、句子裡的網址就是目前這頁 → 不要當成 goto 重開
    session = FakeSession([_view()])
    llm = FakeLLM(["(高) 我在 https://a.test 這裡看看～",  # 沒動作、網址=目前頁
                   "(高) 好了～ [web:done]"])
    op = WebOperator(session, llm, lambda d: True, lambda t: None)
    op.run("看看")
    assert session.executed == []          # 沒有重開同一頁


def test_login_wall_detection():
    # 蝦皮 verify/traffic 那種被擋/登入頁
    assert looks_like_login_wall(
        PageView(url="https://shopee.tw/verify/traffic/error?is_logged_in=false")
    ) is True
    assert looks_like_login_wall(PageView(text="看起來您尚未登入。請登入以繼續，或返回首頁")) is True
    assert looks_like_login_wall(PageView(title="Access Denied")) is True
    # 正常搜尋結果頁不該誤判
    assert looks_like_login_wall(PageView(title="藍牙耳機 - 搜尋結果", text="商品列表 ...")) is False


def test_login_wall_pauses_and_asks_user():
    session = FakeSession([_view(text="看起來您尚未登入。請登入以繼續")])
    llm = FakeLLM(["[web:click;n=0]"] * 5)
    confirms, emits = [], []
    op = WebOperator(session, llm, lambda d: (confirms.append(d), False)[1], emits.append)
    op.run("幫我在蝦皮找藍牙耳機")
    assert session.executed == []
    assert llm.prompts == []
    assert confirms and "登入" in confirms[0]
    assert "不做" in emits[-1]


def test_empty_goal():
    session = FakeSession([_view()])
    llm = FakeLLM([])
    emits = []
    op = WebOperator(session, llm, lambda d: True, emits.append)

    op.run("   ")

    assert session.opened is False
    assert emits and "做什麼" in emits[-1]
