"""Real-browser operation acceptance using routed fixtures, no accounts or LLM."""

import os

import pytest

from doro_app.core.web.operator import WebOperator
from doro_app.core.web.session import WebSession
from doro_app.core.web.web_actions import WebAction, WebStep

pytestmark = pytest.mark.skipif(
    os.environ.get("DORO_BROWSER_TESTS") != "1", reason="opt-in Chromium integration"
)

HTML = """<!doctype html><title>Automation fixture</title>
<label>Category<select id="category"><option>All</option><option>Second</option></select></label>
<label><input id="check" type="checkbox">Include archived</label>
<label>Notes<input id="notes"></label>
<input id="search" type="search" aria-label="Search">
<button id="hover" onmouseover="document.querySelector('#submenu').hidden=false">Menu</button>
<a id="submenu" hidden href="/detail">Detail</a>
<a id="popup" href="/popup" target="_blank">Other tab</a>
<button id="submit" onclick="document.body.dataset.sent='yes'">Submit</button>
<input type="password" value="PRIVATE_PASSWORD">
<textarea>PRIVATE_DRAFT</textarea><div contenteditable>PRIVATE_EDITOR</div>
<p id="status">Waiting</p>
"""


@pytest.fixture
def session(tmp_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        context.route(
            "http://doro.test/**", lambda route: route.fulfill(content_type="text/html", body=HTML)
        )
        page = context.new_page()
        session = WebSession(tmp_path / "isolated", headless=True, nav_timeout_ms=1000)
        session._context, session._page = context, page
        try:
            yield session
        finally:
            session.close()
            browser.close()


def action(kind, **params):
    return WebStep(action=kind, **params).to_action()


def index(session, selector):
    return int(session._page.locator(selector).get_attribute("data-doro-idx"))


def open_fixture(session):
    assert session.goto("http://doro.test/form") is None
    return session.snapshot()


def test_complete_task_from_blank_page_with_forms_wait_and_tabs(session):
    confirmations, replies, prompts = [], [], []
    decisions = iter(["goto", "select", "check", "hover", "wait", "new_tab", "switch_tab", "done"])
    first_tab = session.snapshot().tab_id
    assert session.snapshot().ok

    def ask(prompt):
        prompts.append(prompt)
        kind = next(decisions)
        if kind in {"goto", "new_tab"}:
            return WebStep(
                action=kind,
                url="http://doro.test/form" if kind == "goto" else "http://doro.test/detail",
            )
        if kind == "select":
            return WebStep(action=kind, n=index(session, "#category"), text="Second")
        if kind == "check":
            return WebStep(action=kind, n=index(session, "#check"), checked=True)
        if kind == "hover":
            return WebStep(action=kind, n=index(session, "#hover"))
        if kind == "wait":
            session._page.evaluate(
                "setTimeout(() => document.querySelector('#status').textContent = 'READY', 20)"
            )
            return WebStep(action=kind, seconds=0.1)
        if kind == "switch_tab":
            return WebStep(action=kind, tab_id=first_tab)
        return WebStep(action="done", line="已完成選擇並切回原頁")

    WebOperator(
        session,
        ask,
        lambda text: confirmations.append(text) or True,
        lambda _: None,
        emit_reply=replies.append,
    ).run("選分類、勾選、看另一分頁再回來")
    assert len(confirmations) == 2
    assert replies == ["已完成選擇並切回原頁"]
    assert session._page.locator("#category").input_value() == "Second"
    assert session._page.locator("#check").is_checked()
    assert session._page.locator("#submenu").is_visible()
    assert session._page.locator("#status").inner_text() == "READY"
    assert len(session.list_tabs()) == 2
    assert "READY" in prompts[5]
    for secret in ("PRIVATE_PASSWORD", "PRIVATE_DRAFT", "PRIVATE_EDITOR"):
        assert secret not in "\n".join(prompts)


@pytest.mark.parametrize(
    "mutation",
    [
        "el.replaceWith(el.cloneNode(true))",
        "el.textContent = 'Delete account'",
        "el.hidden = true",
        "el.disabled = true",
    ],
)
def test_confirmation_does_not_authorize_a_changed_target(session, mutation):
    open_fixture(session)
    target = index(session, "#submit")
    calls = [0]

    def ask(_):
        calls[0] += 1
        return (
            WebStep(action="click", n=target)
            if calls[0] == 1
            else WebStep(action="done", line="目標變動，未送出")
        )

    def confirm(_):
        session._page.locator("#submit").evaluate("el => {" + mutation + "}")
        return True

    WebOperator(session, ask, confirm, lambda _: None).run("送出")
    assert session._page.get_attribute("body", "data-sent") is None


def test_removed_indices_cannot_alias_new_elements(session):
    open_fixture(session)
    target = index(session, "#notes")
    session._page.locator("#notes").evaluate("el => el.remove()")
    assert session.execute(action("type", n=target, text="do not type elsewhere"))
    assert session._page.locator("#search").input_value() == ""
    session.snapshot()
    session._page.locator("#check").evaluate("el => el.hidden = true")
    session.snapshot()
    assert session._page.locator("#check").get_attribute("data-doro-idx") is None


def test_input_preserves_whitespace_and_can_clear(session):
    open_fixture(session)
    for text in ("  keep spaces  ", ""):
        session.snapshot()
        assert session.execute(action("type", n=index(session, "#notes"), text=text)) is None
        assert session._page.locator("#notes").input_value() == text


def test_focus_or_search_type_change_rejects_enter(session):
    open_fixture(session)
    session._page.locator("#search").focus()
    session.snapshot()
    session._page.locator("#search").evaluate("el => el.type = 'text'")
    assert "變動" in session.execute(action("press", key="Enter"))
    session.snapshot()
    session._page.locator("#notes").focus()
    assert "變動" in session.execute(action("press", key="Enter"))


def test_navigation_invalidates_old_target(session):
    open_fixture(session)
    target = index(session, "#submit")
    # Same URL and same attributes still refer to a different document.
    session._page.reload()
    assert session.execute(action("click", n=target))
    assert session._page.get_attribute("body", "data-sent") is None


def test_focus_is_captured_with_the_snapshot_not_after_it(session, monkeypatch):
    from doro_app.core.web.session import _CAPTURE_JS

    open_fixture(session)
    session._page.locator("#search").focus()
    original = session._page.evaluate_handle

    def capture_then_change_focus(expression, *args):
        result = original(expression, *args)
        if expression == _CAPTURE_JS:
            session._page.locator("#notes").focus()
        return result

    monkeypatch.setattr(session._page, "evaluate_handle", capture_then_change_focus)
    view = session.snapshot()
    assert next(el for el in view.elements if el["focused"])["input_type"] == "search"
    assert "變動" in session.execute(action("press", key="Enter"))


def test_popup_discovery_and_closed_tab_id_is_never_reused(session):
    first_id = open_fixture(session).tab_id
    with session._page.expect_popup():
        assert session.execute(action("click", n=index(session, "#popup"))) is None
    view = session.snapshot()
    popup_id = next(tab["id"] for tab in view.tabs if tab["id"] != first_id)
    assert session.execute(action("switch_tab", tab_id=popup_id)) is None
    session._page.close()
    assert session.execute(action("switch_tab", tab_id=popup_id))
    assert session.new_tab("http://doro.test/new") is None
    view = session.snapshot()
    assert view.tab_id not in {first_id, popup_id}
    assert session.execute(action("switch_tab", tab_id=first_id)) is None


def test_wrong_control_missing_options_sensitive_fields_and_bad_url_are_rejected(session):
    open_fixture(session)
    assert session.execute(action("select", n=index(session, "#notes"), text="Second"))
    assert session.execute(action("select", n=index(session, "#category"), text="Missing"))
    assert session.execute(action("check", n=index(session, "#notes"), checked=True))
    assert session.execute(action("type", n=index(session, 'input[type="password"]'), text="no"))
    assert session.goto("file:///tmp/private")
    assert session.execute(WebAction("wait", {"seconds": "999"}))
    assert session.execute(WebAction("check", {"n": "0", "checked": "perhaps"}))
    assert session._page.locator('input[type="password"]').input_value() == "PRIVATE_PASSWORD"
