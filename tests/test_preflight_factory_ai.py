"""Startup warns when the asset factory is installed without AI background removal."""

import importlib.util

from doro_app.preflight import preflight_check


def _fake_specs(monkeypatch, installed):
    real = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name in ("cv2", "rembg"):
            return object() if name in installed else None
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


def _ai_warnings(monkeypatch, installed):
    _fake_specs(monkeypatch, installed)
    _, warnings = preflight_check()
    return [w for w in warnings if "AI 去背" in w]


def test_warns_when_factory_installed_without_ai(monkeypatch):
    warnings = _ai_warnings(monkeypatch, {"cv2"})
    assert len(warnings) == 1
    assert "factory-ai" in warnings[0]


def test_quiet_when_ai_is_installed(monkeypatch):
    assert _ai_warnings(monkeypatch, {"cv2", "rembg"}) == []


def test_quiet_when_factory_is_not_installed(monkeypatch):
    assert _ai_warnings(monkeypatch, set()) == []
