"""Real Chromium tests, opt in with DORO_BROWSER_TESTS=1 (no accounts or LLM)."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DORO_BROWSER_TESTS") != "1", reason="opt-in Chromium integration"
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"""<!doctype html><title>{self.path}</title><main><h1>Visible {self.path}</h1>
        <p id="article">Article content</p><input type="password" value="FAKE_PASSWORD">
        <input value="PRIVATE_INPUT"><textarea>PRIVATE_DRAFT</textarea>
        <div contenteditable>PRIVATE_EDITOR</div><p hidden>HIDDEN_TEXT</p>
        <input type="search" id="search"><form><button id="submit">Continue</button></form></main>""".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture
def website():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def eventually(page, predicate, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        page.wait_for_timeout(50)
    assert predicate(), "expected browser/bridge state did not arrive"


def test_actual_snapshot_redacts_values_and_identifies_submit(tmp_path, website):
    from playwright.sync_api import sync_playwright

    from doro_app.core.web.session import _SNAPSHOT_JS, WebSession
    from doro_app.core.web.web_actions import needs_confirmation, parse_web_action

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(website + "/one")
            page.locator("#search").focus()
            elements = page.evaluate(_SNAPSHOT_JS)
            assert "FAKE_PASSWORD" not in str(elements)
            assert "PRIVATE_INPUT" not in str(elements)
            assert any(el["sensitive"] for el in elements)
            assert not needs_confirmation(
                parse_web_action("[web:press;key=Enter]"), elements=elements
            )
            submit = next(el for el in elements if el["name"] == "Continue")
            assert needs_confirmation(
                parse_web_action(f"[web:click;n={submit['idx']}]"),
                {submit["idx"]: "Continue"},
                elements=elements,
            )
            session = WebSession(tmp_path)
            session._context = page.context
            session._page = page
            password = next(el for el in elements if el["sensitive"])
            assert session.type_index(password["idx"], "ATTEMPT") is not None
            assert page.locator('input[type="password"]').input_value() == "FAKE_PASSWORD"
        finally:
            browser.close()


def test_extension_focus_content_and_pause(tmp_path, website):
    from playwright.sync_api import sync_playwright

    from doro_app.core.presence.bridge import PresenceBridge

    extension = Path(__file__).resolve().parents[2] / "extensions" / "doro-presence"
    events = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            tmp_path / "profile",
            channel="chromium",
            headless=True,
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
        )
        bridge = None
        try:
            worker = (
                context.service_workers[0]
                if context.service_workers
                else context.wait_for_event("serviceworker")
            )
            extension_id = worker.url.split("/")[2]
            bridge = PresenceBridge(extension_id, "T" * 43, events.append, port=0)
            bridge.start()
            worker.evaluate(
                "s => chrome.storage.local.set(s)",
                {"enabled": True, "token": "T" * 43, "port": bridge.port},
            )
            page = context.new_page()
            page.goto(website + "/one")
            page.bring_to_front()
            eventually(page, lambda: bridge.current_page is not None)
            assert bridge.current_page.url.endswith("/one")
            content = bridge.current_page.text
            assert "Visible /one" in content
            for secret in (
                "FAKE_PASSWORD",
                "PRIVATE_INPUT",
                "PRIVATE_DRAFT",
                "PRIVATE_EDITOR",
                "HIDDEN_TEXT",
            ):
                assert secret not in content
            page.locator("#article").evaluate("el => el.textContent = 'NEW_VISIBLE_FACT'")
            eventually(
                page, lambda: bridge.current_page and "NEW_VISIBLE_FACT" in bridge.current_page.text
            )
            # Attribute-only changes must refresh the bridge, including editor
            # transitions which must remove text from the shared snapshot.
            for attribute, value in (
                ("hidden", ""),
                ("style", "display: none"),
                ("aria-hidden", "true"),
                ("contenteditable", "true"),
            ):
                page.locator("#article").evaluate(
                    "(el, pair) => el.setAttribute(...pair)",
                    [attribute, value],
                )
                eventually(
                    page,
                    lambda: bridge.current_page
                    and "NEW_VISIBLE_FACT" not in bridge.current_page.text,
                )
                page.locator("#article").evaluate(
                    "(el, name) => el.removeAttribute(name)",
                    attribute,
                )
                eventually(
                    page,
                    lambda: bridge.current_page and "NEW_VISIBLE_FACT" in bridge.current_page.text,
                )
            page.add_style_tag(content=".collapsed { display: none; }")
            page.locator("#article").evaluate("el => el.classList.add('collapsed')")
            eventually(
                page,
                lambda: bridge.current_page and "NEW_VISIBLE_FACT" not in bridge.current_page.text,
            )
            page.locator("#article").evaluate("el => el.classList.remove('collapsed')")
            eventually(
                page, lambda: bridge.current_page and "NEW_VISIBLE_FACT" in bridge.current_page.text
            )
            second = context.new_page()
            second.goto(website + "/two")
            second.bring_to_front()
            eventually(
                second, lambda: bridge.current_page and bridge.current_page.url.endswith("/two")
            )
            page.locator("#article").evaluate("el => el.textContent = 'BACKGROUND_CHANGE'")
            second.wait_for_timeout(150)
            assert bridge.current_page.url.endswith("/two")
            assert "BACKGROUND_CHANGE" not in bridge.current_page.text
            # Restart the local app bridge; extension must reconnect and resend
            # the current page even if its text hasn't changed.
            bridge.shutdown()
            assert bridge.current_page is None
            bridge.start()
            eventually(
                second, lambda: bridge.current_page and bridge.current_page.url.endswith("/two")
            )
            worker.evaluate("() => chrome.storage.local.set({enabled:false})")
            eventually(second, lambda: bridge.current_page is None)
        finally:
            context.close()
            if bridge:
                bridge.shutdown()


def test_web_session_uses_native_window_viewport(tmp_path):
    from playwright.sync_api import sync_playwright
    from doro_app.core.web.session import WebSession

    session = WebSession(tmp_path / "profile", headless=True, browser_channel=None)
    with sync_playwright() as playwright:
        session._pw = playwright
        context = session._launch_context(None)
        try:
            assert context.pages[0].viewport_size is None
            assert context.new_page().viewport_size is None
        finally:
            context.close()
