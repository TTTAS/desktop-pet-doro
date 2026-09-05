"""查證管線 `verify` 的測試（全用假物件，不上網、不呼叫 AI）。"""

from __future__ import annotations

from doro_app.core.web.session import PageView
import base64

from doro_app.core.web.verify import (
    VerifyPipeline,
    build_search_url,
    pick_result_links,
    resolve_redirect,
)


def _bing_ck(real_url: str) -> str:
    enc = base64.urlsafe_b64encode(real_url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=xyz&u=a1{enc}"


class FakeVerifySession:
    def __init__(self, views, links, *, goto_fail=()):
        self._views = list(views)
        self._links = list(links)
        self._goto_fail = set(goto_fail)
        self.goto_urls = []

    def ensure_open(self):
        return None

    def goto(self, url):
        self.goto_urls.append(url)
        return "打不開" if url in self._goto_fail else None

    def snapshot(self):
        return self._views.pop(0) if self._views else PageView(error="no more")

    def collect_links(self):
        return self._links


def _links(*urls):
    return [{"url": u, "text": f"連結 {i}"} for i, u in enumerate(urls)]


class TestHelpers:
    def test_build_search_url_uses_bing(self):
        url = build_search_url("藍牙耳機 推薦")
        assert url.startswith("https://www.bing.com/search?q=")
        assert "%E8" in url  # query 有被 url-encode

    def test_resolve_bing_redirect(self):
        assert resolve_redirect(_bing_ck("https://shopee.tw/doro-goods")) == "https://shopee.tw/doro-goods"
        assert resolve_redirect("https://a.com/plain") == "https://a.com/plain"

    def test_pick_resolves_bing_redirects(self):
        # Bing 把結果連結包成 bing.com/ck/a → 還原後才不會被當成 bing 自己而被濾掉
        links = [
            {"url": _bing_ck("https://shopee.tw/doro"), "text": "蝦皮 doro"},
            {"url": _bing_ck("https://momoshop.com.tw/doro"), "text": "momo doro"},
        ]
        picked = pick_result_links(links, max_sources=3)
        assert [p["url"] for p in picked] == ["https://shopee.tw/doro", "https://momoshop.com.tw/doro"]

    def test_pick_filters_search_engines_and_dedups_domain(self):
        links = _links(
            "https://www.bing.com/ad",          # 搜尋引擎自己 → 跳過
            "https://a.example.com/1",
            "https://a.example.com/2",           # 同網域 → 只留一個
            "https://b.example.com/3",
            "https://facebook.com/x",            # 社群 → 跳過
        )
        picked = pick_result_links(links, max_sources=3)
        doms = [u["url"] for u in picked]
        assert doms == ["https://a.example.com/1", "https://b.example.com/3"]


class TestVerifyPipeline:
    def _search_view(self):
        return PageView(url="https://www.bing.com/search?q=x", title="搜尋", text="結果列表")

    def test_happy_path(self):
        views = [
            self._search_view(),
            PageView(url="https://a.com/1", title="來源A", text="基本工資是 28590 元"),
            PageView(url="https://b.com/2", title="來源B", text="月薪最低 28590"),
        ]
        session = FakeVerifySession(views, _links("https://a.com/1", "https://b.com/2"))
        progress, final = [], []
        VerifyPipeline(session, lambda p: "(高) 兩個來源都說 28590 元～", progress.append, final.append).run("基本工資")
        assert final and "28590" in final[0]
        assert progress == []  # 機械進度不再進泡泡（收到後台 _dbg）

    def test_prompt_contains_sources(self):
        captured = {}
        views = [
            self._search_view(),
            PageView(url="https://a.com/1", title="來源A", text="內容甲"),
        ]
        session = FakeVerifySession(views, _links("https://a.com/1"))
        def ask(p):
            captured["prompt"] = p
            return "答案"
        VerifyPipeline(session, ask, lambda t: None, lambda t: None).run("問題X")
        assert "問題X" in captured["prompt"]
        assert "來源A" in captured["prompt"] and "內容甲" in captured["prompt"]

    def test_no_links_reports_not_found(self):
        session = FakeVerifySession([self._search_view()], [])
        final = []
        VerifyPipeline(session, lambda p: "x", lambda t: None, final.append).run("找不到的東西")
        assert "找不到" in final[-1]

    def test_search_blocked(self):
        blocked = PageView(url="https://www.bing.com/sorry", title="reCAPTCHA", text="verify")
        session = FakeVerifySession([blocked], _links("https://a.com/1"))
        final = []
        VerifyPipeline(session, lambda p: "x", lambda t: None, final.append).run("x")
        assert "擋" in final[-1]

    def test_all_sources_unreadable(self):
        views = [
            self._search_view(),
            PageView(url="https://a.com/1", title="", text="", error=None),  # 空內容
            PageView(url="https://b.com/2", title="登入", text="請登入以繼續"),  # 登入牆
        ]
        session = FakeVerifySession(views, _links("https://a.com/1", "https://b.com/2"))
        final = []
        VerifyPipeline(session, lambda p: "x", lambda t: None, final.append).run("x")
        assert "讀不到" in final[-1]

    def test_empty_query(self):
        session = FakeVerifySession([self._search_view()], [])
        final = []
        VerifyPipeline(session, lambda p: "x", lambda t: None, final.append).run("   ")
        assert final and "查什麼" in final[-1]
