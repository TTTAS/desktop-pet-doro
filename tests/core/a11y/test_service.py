"""Tests for A11yService gating, redaction wiring, and timeout handling."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from doro_app.constants import (
    A11Y_INVOKE_TIMEOUT_SECONDS,
    A11Y_READ_TIMEOUT_SECONDS,
    A11Y_TIMEOUT_BLACKLIST_THRESHOLD,
)
from doro_app.core.a11y.fakes import FakeA11yBackend
from doro_app.core.a11y.models import A11yElement
from doro_app.core.a11y.service import A11yService


def _config(enabled=True, blacklist=(), share_input_values=True):
    # Default the new gate to True so existing tests — which were
    # written before input-value redaction was opt-in — keep asserting
    # against the same serialized output. New tests can pass
    # share_input_values=False to exercise the redaction path.
    return SimpleNamespace(
        automation=SimpleNamespace(
            a11y_enabled=enabled,
            a11y_app_blacklist=tuple(blacklist),
            a11y_share_input_values=share_input_values,
        )
    )


def _make_service(backend, *, config=None, handle=1234, window_cls="Chrome", audit_path=None):
    return A11yService(
        config_manager=config or _config(),
        backend=backend,
        handle_provider=lambda: handle,
        class_provider=lambda h: window_cls,
        audit_path=audit_path,
    )


def _button(name="書籤", x=1850, y=80):
    return A11yElement(role="button", name=name, x=x, y=y, width=24, height=24)


@pytest.fixture
def audit_file(tmp_path):
    return tmp_path / "share_audit.log"


class TestGating:
    def test_disabled_returns_empty_and_skips_backend(self, audit_file):
        backend = FakeA11yBackend([_button()])
        svc = _make_service(backend, config=_config(enabled=False), audit_path=audit_file)
        assert svc.read_foreground_tree() == ""
        assert backend.read_calls == []

    def test_no_foreground_handle_returns_empty(self, audit_file):
        backend = FakeA11yBackend([_button()])
        svc = _make_service(backend, handle=None, audit_path=audit_file)
        assert svc.read_foreground_tree() == ""
        assert backend.read_calls == []

    def test_blacklisted_class_returns_empty_and_audits(self, audit_file):
        backend = FakeA11yBackend([_button()])
        svc = _make_service(
            backend,
            config=_config(blacklist=("KeePass",)),
            window_cls="Qt.KeePassXC.Window",
            audit_path=audit_file,
        )
        assert svc.read_foreground_tree() == ""
        assert backend.read_calls == []
        assert "BLACKLISTED" in audit_file.read_text(encoding="utf-8")


class TestHappyPath:
    def test_returns_header_and_serialized_body(self, audit_file):
        backend = FakeA11yBackend([_button("書籤", 1850, 80)])
        svc = _make_service(backend, audit_path=audit_file)
        out = svc.read_foreground_tree()
        assert out.startswith("[前景視窗元件樹]\n")
        assert 'button "書籤" (1850,80 24x24)' in out
        assert backend.read_calls == [1234]

    def test_successful_read_is_audited(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button()]), audit_path=audit_file)
        svc.read_foreground_tree()
        text = audit_file.read_text(encoding="utf-8")
        assert "read" in text
        assert "Chrome" in text

    def test_password_value_is_redacted_in_output(self, audit_file):
        secret = A11yElement(
            role="input", name="pw", x=0, y=0, width=100, height=20,
            value="hunter2", is_password=True,
        )
        svc = _make_service(FakeA11yBackend([secret]), audit_path=audit_file)
        out = svc.read_foreground_tree()
        assert "hunter2" not in out
        assert "[redacted-password]" in out


class TestBoundsAtPhysicalPoint:
    """The click warning overlay calls this at wind-up time with Doro's foot
    position to frame the a11y element the click will land on."""

    def test_none_when_no_read(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button()]), audit_path=audit_file)
        assert svc.bounds_at_physical_point(100, 100) is None

    def test_returns_bounds_when_point_inside_element(self, audit_file):
        # _button() defaults to (100, 200) and 24x24 → covers x∈[100,124), y∈[200,224).
        svc = _make_service(
            FakeA11yBackend([_button("ok", 100, 200)]), audit_path=audit_file
        )
        svc.read_foreground_tree()
        assert svc.bounds_at_physical_point(110, 210) == (100, 200, 24, 24)

    def test_returns_none_when_point_outside_any_element(self, audit_file):
        svc = _make_service(
            FakeA11yBackend([_button("ok", 100, 200)]), audit_path=audit_file
        )
        svc.read_foreground_tree()
        assert svc.bounds_at_physical_point(0, 0) is None
        # On the right/bottom edge is "outside" (half-open interval).
        assert svc.bounds_at_physical_point(124, 224) is None

    def test_returns_smallest_match_when_nested(self, audit_file):
        # Outer container covers (0,0)–(1000,1000); inner button covers
        # (100,200)–(124,224). A point inside both should resolve to the
        # smaller (inner) button.
        outer = A11yElement(role="group", name="toolbar", x=0, y=0, width=1000, height=1000)
        inner = _button("ok", 100, 200)
        svc = _make_service(FakeA11yBackend([outer, inner]), audit_path=audit_file)
        svc.read_foreground_tree()
        assert svc.bounds_at_physical_point(110, 210) == (100, 200, 24, 24)


class TestEmptyResults:
    def test_backend_none_returns_empty(self, audit_file):
        backend = FakeA11yBackend(return_none=True)
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.read_foreground_tree() == ""

    def test_no_interactable_elements_returns_empty(self, audit_file):
        deco = A11yElement(role="pane", name="bg", x=0, y=0, width=5, height=5)
        svc = _make_service(FakeA11yBackend([deco]), audit_path=audit_file)
        assert svc.read_foreground_tree() == ""


class TestDiagnose:
    def test_disabled_reason(self, audit_file):
        svc = _make_service(
            FakeA11yBackend([_button()]), config=_config(enabled=False), audit_path=audit_file
        )
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "未啟用" in msg

    def test_no_handle_reason(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button()]), handle=None, audit_path=audit_file)
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "前景視窗" in msg

    def test_blacklisted_reason(self, audit_file):
        svc = _make_service(
            FakeA11yBackend([_button()]),
            config=_config(blacklist=("KeePass",)),
            window_cls="Qt.KeePassXC.Window",
            audit_path=audit_file,
        )
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "黑名單" in msg

    def test_backend_none_reason(self, audit_file):
        svc = _make_service(FakeA11yBackend(return_none=True), audit_path=audit_file)
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "讀不到元件樹" in msg

    def test_no_interactable_reason(self, audit_file):
        deco = A11yElement(role="pane", name="bg", x=0, y=0, width=5, height=5)
        svc = _make_service(FakeA11yBackend([deco]), audit_path=audit_file)
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "可互動元件" in msg

    def test_success_returns_serialized_body(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button("書籤", 1850, 80)]), audit_path=audit_file)
        ok, body = svc.diagnose_foreground_tree()
        assert ok is True
        assert 'button "書籤" (1850,80 24x24)' in body

    def test_diagnose_does_not_write_audit(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button()]), audit_path=audit_file)
        svc.diagnose_foreground_tree()
        assert not audit_file.exists()


class TestDiagnoseDetails:
    def test_none_reason_includes_backend_last_error(self, audit_file):
        backend = FakeA11yBackend(return_none=True)
        backend.last_error = "ControlFromHandle 取不到視窗根節點（handle=999）"
        svc = _make_service(backend, audit_path=audit_file)
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "ControlFromHandle" in msg

    def test_empty_chrome_includes_renderer_hint_and_count(self, audit_file):
        deco = A11yElement(role="pane", name="bg", x=0, y=0, width=5, height=5)
        backend = FakeA11yBackend([deco])
        backend.last_visited = 42
        svc = _make_service(backend, window_cls="Chrome_WidgetWin_1", audit_path=audit_file)
        ok, msg = svc.diagnose_foreground_tree()
        assert ok is False
        assert "chrome://accessibility" in msg
        assert "42" in msg


class TestTimeout:
    def test_slow_read_times_out_to_empty(self, audit_file):
        # A read slower than the live budget is abandoned and yields "".
        backend = FakeA11yBackend([_button()], delay=A11Y_READ_TIMEOUT_SECONDS + 0.2)
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.read_foreground_tree() == ""

    def test_repeated_timeouts_blacklist_class_for_session(self, audit_file):
        # Drive the timeout path directly with a tiny budget so the test is fast
        # and independent of the live constant.
        backend = FakeA11yBackend([_button()], delay=0.1)
        svc = _make_service(backend, window_cls="LaggyApp", audit_path=audit_file)

        for _ in range(A11Y_TIMEOUT_BLACKLIST_THRESHOLD):
            assert svc._read_with_timeout(1234, "laggyapp", timeout=0.01) is None

        assert "laggyapp" in svc._session_blacklist

        calls_before = len(backend.read_calls)
        # Session-blacklisted class must not hit the backend on the public read.
        assert svc.read_foreground_tree() == ""
        assert len(backend.read_calls) == calls_before

    def test_success_resets_timeout_streak(self, audit_file):
        backend = FakeA11yBackend([_button()])
        svc = _make_service(backend, window_cls="App", audit_path=audit_file)
        svc._timeout_counts["app"] = 2
        svc.read_foreground_tree()
        assert "app" not in svc._timeout_counts


class TestInvokeTimeout:
    """UIA `Invoke()` can hang waiting for a modal — the executor +
    timeout ensures the chat thread doesn't freeze with it."""

    def test_slow_invoke_times_out_to_false(self, audit_file):
        backend = FakeA11yBackend(
            [_button()],
            invoke_delay=A11Y_INVOKE_TIMEOUT_SECONDS + 0.2,
        )
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.invoke_at_point(100, 100) is False

    def test_fast_invoke_returns_backend_result(self, audit_file):
        backend = FakeA11yBackend([_button()], invoke_succeeds=True)
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.invoke_at_point(100, 100) is True

    def test_invoke_self_gates_on_a11y_enabled(self, audit_file):
        backend = FakeA11yBackend([_button()], invoke_succeeds=True)
        svc = _make_service(
            backend,
            config=_config(enabled=False),
            audit_path=audit_file,
        )
        assert svc.invoke_at_point(100, 100) is False
        # Backend should not have been touched.
        assert backend.invoke_calls == []


class TestPreviewTimeout:
    def test_preview_uses_longer_budget_than_live(self, audit_file):
        # A tree that's too slow for the live budget still completes for preview.
        delay = A11Y_READ_TIMEOUT_SECONDS + 0.2
        svc = _make_service(FakeA11yBackend([_button()], delay=delay), audit_path=audit_file)
        assert svc.read_foreground_tree() == ""
        ok, body = svc.diagnose_foreground_tree()
        assert ok is True
        assert "button" in body

    def test_preview_timeout_does_not_blacklist(self, audit_file):
        backend = FakeA11yBackend([_button()], delay=0.1)
        svc = _make_service(backend, window_cls="LaggyApp", audit_path=audit_file)
        for _ in range(A11Y_TIMEOUT_BLACKLIST_THRESHOLD + 1):
            assert (
                svc._read_with_timeout(1234, "laggyapp", timeout=0.01, count_timeout=False)
                is None
            )
        assert svc._session_blacklist == set()
        assert svc._timeout_counts == {}


class TestClearBlacklist:
    def test_clear_session_blacklist(self, audit_file):
        svc = _make_service(FakeA11yBackend([_button()]), audit_path=audit_file)
        svc._session_blacklist.add("foo")
        svc._timeout_counts["foo"] = 2
        svc.clear_session_blacklist()
        assert svc._session_blacklist == set()
        assert svc._timeout_counts == {}
