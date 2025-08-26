import requests
import os
from types import SimpleNamespace

import pytest

from src.requester import prepare_params, send_request


class DummyResp:
    def __init__(self, status_code=200, json_obj=None, text=""):
        self.status_code = status_code
        self._json = json_obj
        self.text = text

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


class DummySession:
    def __init__(self, resp=None, exc=None):
        self.headers = {}
        self.params = None
        self._resp = resp
        self._exc = exc
        self.request_called_with = None

    def request(self, method, url, params=None, timeout=None, **kwargs):
        # 记录调用参数，便于断言
        self.request_called_with = {"method": method, "url": url, "params": params, "timeout": timeout, **kwargs}
        if self._exc:
            raise self._exc
        return self._resp


def test_prepare_params_merges_and_injects_api_key(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "ENVKEY123")
    sess = SimpleNamespace(params={"a": 1})
    out = prepare_params(sess, {"b": 2}, "v3")
    assert out["a"] == 1
    assert out["b"] == 2
    assert out["api_key"] == "ENVKEY123"


def test_prepare_params_no_inject_for_v4(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "ENVKEY123")
    sess = SimpleNamespace(params=None, headers={"Authorization": "Bearer TOKEN"})
    out = prepare_params(sess, {"b": 2}, "v4")
    assert "api_key" not in out
    assert out["b"] == 2


def test_send_request_timeout():
    sess = DummySession(resp=None, exc=requests.Timeout())
    res = send_request(sess, "https://api.test", "GET", "/ok")
    assert res["success"] is False
    assert res["error"] and "超时" in res["error"]


def test_send_request_injects_api_key_into_request(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "KEY123")
    resp = DummyResp(200, json_obj={"results": [{"id": 1}]})
    sess = DummySession(resp=resp)
    res = send_request(sess, "https://api.test", "GET", "/movies")
    # ensure request was called and api_key was passed to params
    assert sess.request_called_with is not None
    params = sess.request_called_with.get("params") or {}
    assert params.get("api_key") == "KEY123"
    assert res["success"] is True
    assert isinstance(res["results"], list)


def test_send_request_204_no_content():
    resp = DummyResp(204, json_obj=None, text="")
    sess = DummySession(resp=resp)
    res = send_request(sess, "https://api.test", "GET", "/none")
    assert res["success"] is True
    assert res["data"] is None
    assert res["results"] == []


def test_send_request_http_error_with_json_message():
    resp = DummyResp(400, json_obj={"status_message": "bad request"})
    sess = DummySession(resp=resp)
    res = send_request(sess, "https://api.test", "GET", "/bad")
    assert res["success"] is False
    assert res["status_code"] == 400
    assert "bad request" in str(res["error"])
    assert res["data"] == {"status_message": "bad request"}


def test_send_request_success_with_list_data():
    resp = DummyResp(200, json_obj=[1, 2, 3])
    sess = DummySession(resp=resp)
    res = send_request(sess, "https://api.test", "GET", "/list")
    assert res["success"] is True
    assert res["results"] == [1, 2, 3]
    assert res["data"] == [1, 2, 3]