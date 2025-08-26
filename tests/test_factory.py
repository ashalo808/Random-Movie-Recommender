import os
import types
import pytest

from src import factory


def test_create_client_no_key_raises(monkeypatch):
    # 确保环境变量和 config.get_tmdb_key 都不可用
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.setattr(factory, "get_tmdb_key", lambda: None)
    with pytest.raises(ValueError):
        factory.create_client(api_key=None)


def test_create_client_cache_and_session_factory(monkeypatch):
    created = []

    class DummySession:
        def __init__(self):
            self.headers = {}
            self.proxies = {}
            self.verify = True

    class DummyClient:
        def __init__(self, base_url, api_key, key_type, timeout, max_retries):
            # 记录构造参数，模拟真实 ApiClient
            created.append((base_url, api_key, key_type, timeout, max_retries))
            self.session = DummySession()

    # 替换 factory 中的 ApiClient 为 DummyClient，避免真实网络
    monkeypatch.setattr(factory, "ApiClient", DummyClient)

    # 强制提供 api_key，第一次创建并缓存
    c1 = factory.create_client(api_key="KEY123", reuse_cache=True)
    # 再次创建应返回缓存实例
    c2 = factory.create_client(api_key="KEY123", reuse_cache=True)
    assert c1 is c2
    assert created, "DummyClient 没有被构造"

    # 测试 session_factory 注入
    def session_factory():
        s = DummySession()
        s.headers["X-Test"] = "yes"
        return s

    c3 = factory.create_client(api_key="KEY123", session_factory=session_factory, reuse_cache=False)
    assert hasattr(c3, "session")
    assert c3.session.headers.get("X-Test") == "yes"


def test_fetch_popular_quick_and_search_quick(monkeypatch):
    ts_holder = {}

    class FakeClient:
        def fetch_popular(self, page):
            return {"success": True, "results": [{"id": 1, "title": "A"}]}

        def search_movies(self, query, page):
            return {"success": True, "results": [{"id": 2, "title": query}]}

    # 让 create_client 返回 FakeClient 实例
    monkeypatch.setattr(factory, "create_client", lambda api_key, **kw: FakeClient())

    resp = factory.fetch_popular_quick("KEYX", page=2)
    assert resp.get("success") is True
    assert isinstance(resp.get("results"), list)
    assert resp["_query_info"]["page"] == 2

    resp2 = factory.search_quick("KEYX", "matrix", page=1)
    assert resp2.get("success") is True
    assert resp2["_query_info"]["query"] == "matrix"


# optional: ensure search_quick rejects empty query
def test_search_quick_empty_query():
    r = factory.search_quick("KEY", "", page=1)
    assert r["success"] is False
    assert "query 不能为空"