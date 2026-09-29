from doro_app.core.web.operator import WebOperator
from doro_app.core.web.session import PageView
from doro_app.core.web.web_actions import WebStep, needs_confirmation, parse_web_action


class Session:
    def __init__(self, elements=None):
        self.executed = []
        self.elements = elements or [{"idx": 0, "name": "Next"}]

    def ensure_open(self):
        return None

    def snapshot(self):
        return PageView(url="https://example.test", elements=self.elements)

    def execute(self, action):
        self.executed.append(action)


def test_cancel_during_model_does_not_execute():
    session, stopped = Session(), [False]

    def ask(_):
        stopped[0] = True
        return WebStep(action="click", n=0)

    WebOperator(session, ask, lambda _: True, lambda _: None, should_cancel=lambda: stopped[0]).run(
        "next"
    )
    assert session.executed == []


def test_cancel_after_confirmation_does_not_execute():
    session, stopped = Session([{"idx": 0, "name": "Submit"}]), [False]

    def confirm(_):
        stopped[0] = True
        return True

    WebOperator(
        session,
        lambda _: WebStep(action="click", n=0),
        confirm,
        lambda _: None,
        should_cancel=lambda: stopped[0],
    ).run("submit")
    assert session.executed == []


def test_password_cannot_be_filled_by_model():
    session = Session([{"idx": 0, "name": "Password", "sensitive": True}])
    WebOperator(
        session,
        lambda _: WebStep(action="type", n=0, text="FAKE_SECRET"),
        lambda _: True,
        lambda _: None,
    ).run("fill")
    assert session.executed == []


def test_unknown_and_submit_controls_require_confirmation():
    click = parse_web_action("[web:click;n=0]")
    assert needs_confirmation(click, {0: ""})
    assert needs_confirmation(click, {0: "Continue"}, elements=[{"idx": 0, "is_submit": True}])
    for key in ("Enter", "Control+Enter", "Meta+Enter", "Space"):
        assert needs_confirmation(
            parse_web_action(f"[web:press;key={key}]"), {}, "https://example.test/messages"
        )


def test_final_line_goes_to_the_presenter():
    replies = []
    session = Session()
    finish = WebStep(action="done", line="找到了！")
    WebOperator(
        session, lambda _: finish, lambda _: True, lambda _: None, emit_reply=replies.append
    ).run("find")
    assert replies == ["找到了！"]
    assert session.executed == []
