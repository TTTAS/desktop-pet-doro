"""``WebPageReader`` 的測試。

真正開瀏覽器的路徑需要 Playwright + Chromium，這裡只測「不需要真的上網」也
能驗證的行為：

- 空網址 → 回錯誤，不會炸。
- 沒安裝 Playwright → 回友善的安裝指引（而不是丟例外）。

真正開瀏覽器讀網頁的驗證，走手動/整合測試（見 tests/manual）。
"""

from __future__ import annotations

import builtins

import pytest

from doro_app.core.web.reader import WebPageReader


def test_empty_url_returns_error(tmp_path):
    reader = WebPageReader(tmp_path / "profile")
    result = reader.read("")
    assert not result.ok
    assert result.error


def test_missing_playwright_returns_install_hint(tmp_path, monkeypatch):
    """模擬未安裝 Playwright：import 失敗時要回安裝指引，不能拋例外。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    reader = WebPageReader(tmp_path / "profile")
    result = reader.read("https://example.com")
    assert not result.ok
    assert "playwright" in (result.error or "").lower()
