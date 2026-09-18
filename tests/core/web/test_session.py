"""`WebSession` 不需要真的開瀏覽器也能驗證的部分。

真正開瀏覽器操作的驗證走手動/整合測試。這裡只確認：
- 沒裝 Playwright 時 ``ensure_open`` 回安裝指引、不炸。
- 還沒開瀏覽器就呼叫操作，會回友善錯誤而不是例外。
- ``PageView.element_names`` 對照表正確。
"""

from __future__ import annotations

import builtins

from doro_app.core.web.session import PageView, WebSession


def test_element_names_mapping():
    view = PageView(elements=[{"idx": 0, "name": "搜尋"}, {"idx": 1, "name": "登入"}])
    assert view.element_names() == {0: "搜尋", 1: "登入"}


def test_actions_before_open_return_error(tmp_path):
    s = WebSession(tmp_path / "profile")
    assert s.is_open is False
    assert s.snapshot().error
    assert s.click_index(0) is not None
    assert s.goto("https://a.test") is not None


def test_closed_window_error_message(tmp_path):
    # Playwright 「視窗被關掉」的錯誤字樣 → 回友善「被關掉」訊息
    s = WebSession(tmp_path / "profile")
    msg = s._error_or_closed(Exception("Target page, context or browser has been closed"), "點擊")
    assert "關掉" in msg


def test_ensure_open_without_playwright(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    s = WebSession(tmp_path / "profile")
    err = s.ensure_open()
    assert err and "playwright" in err.lower()
    assert s.is_open is False
