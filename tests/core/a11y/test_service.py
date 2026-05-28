"""Tests for A11yService gating, redaction wiring, and timeout handling."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from doro_app.constants import A11Y_TIMEOUT_BLACKLIST_THRESHOLD
from doro_app.core.a11y.fakes import FakeA11yBackend
from doro_app.core.a11y.models import A11yElement
from doro_app.core.a11y.service import A11yService


def _config(enabled=True, blacklist=()):
    return SimpleNamespace(
        automation=SimpleNamespace(a11y_enabled=enabled, a11y_app_blacklist=tuple(blacklist))
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


class TestEmptyResults:
    def test_backend_none_returns_empty(self, audit_file):
        backend = FakeA11yBackend(return_none=True)
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.read_foreground_tree() == ""

    def test_no_interactable_elements_returns_empty(self, audit_file):
        deco = A11yElement(role="pane", name="bg", x=0, y=0, width=5, height=5)
        svc = _make_service(FakeA11yBackend([deco]), audit_path=audit_file)
        assert svc.read_foreground_tree() == ""


class TestTimeout:
    def test_slow_read_times_out_to_empty(self, audit_file):
        backend = FakeA11yBackend([_button()], delay=0.3)
        svc = _make_service(backend, audit_path=audit_file)
        assert svc.read_foreground_tree() == ""

    def test_repeated_timeouts_blacklist_class_for_session(self, audit_file):
        backend = FakeA11yBackend([_button()], delay=0.3)
        svc = _make_service(backend, window_cls="LaggyApp", audit_path=audit_file)

        for _ in range(A11Y_TIMEOUT_BLACKLIST_THRESHOLD):
            assert svc.read_foreground_tree() == ""

        assert "laggyapp" in svc._session_blacklist

        calls_before = len(backend.read_calls)
        assert svc.read_foreground_tree() == ""
        # Session-blacklisted class must not hit the backend again.
        assert len(backend.read_calls) == calls_before

    def test_success_resets_timeout_streak(self, audit_file):
        backend = FakeA11yBackend([_button()])
        svc = _make_service(backend, window_cls="App", audit_path=audit_file)
        svc._timeout_counts["app"] = 2
        svc.read_foreground_tree()
        assert "app" not in svc._timeout_counts
