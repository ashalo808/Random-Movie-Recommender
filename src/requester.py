import logging
import requests
import os
from typing import Any
from config import get_tmdb_key

logger = logging.getLogger(__name__)

def prepare_params(session, params: dict | None, key_type: str) -> dict:
    """
    合并并返回用于请求的查询参数。
    优先使用 session.params -> params；当 key_type == "v3" 且无 api_key 时，
    回退到环境变量 TMDB_API_KEY 或 config.get_tmdb_key()。
    """
    merged: dict[str, Any] = {}

    sess_params = getattr(session, "params", None)
    if isinstance(sess_params, dict):
        merged.update(sess_params)

    if isinstance(params, dict):
        merged.update(params)

    if key_type == "v3" and "api_key" not in merged:
        api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
        if api_key:
            merged["api_key"] = str(api_key)

    return merged

def send_request(session, base_url: str, method: str, endpoint: str, params: dict | None = None, timeout: float = 10.0, **kwargs) -> dict:
    """
    发送 HTTP 请求并返回统一结构化结果。

    额外的 body/json/headers 等会透传到 session.request（通过 kwargs）。
    返回结构始终包含: success, status_code, data, results, error。
    """
    url = f"{base_url.rstrip('/')}/{str(endpoint).lstrip('/')}"
    sess_params = getattr(session, "params", None)
    headers = getattr(session, "headers", {}) or {}
    if isinstance(sess_params, dict) and "api_key" in sess_params:
        key_type = "v3"
    elif isinstance(headers, dict) and headers.get("Authorization", "").startswith("Bearer "):
        key_type = "v4"
    else:
        key_type = "v3"

    merged_params = prepare_params(session, params, key_type)

    try:
        resp = session.request(method.upper(), url, params=merged_params, timeout=timeout, **kwargs)
    except requests.Timeout as e:
        logger.debug("requester.send_request timeout %s %s: %s", method, url, e)
        return {"success": False, "status_code": None, "data": None, "results": [], "error": "请求超时"}
    except requests.ConnectionError as e:
        logger.debug("requester.send_request connection error %s %s: %s", method, url, e)
        return {"success": False, "status_code": None, "data": None, "results": [], "error": "网络连接错误"}
    except requests.RequestException as e:
        logger.debug("requester.send_request request exception %s %s: %s", method, url, e)
        return {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}
    except Exception as e:
        logger.exception("requester.send_request 未知异常")
        return {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}

    status = getattr(resp, "status_code", None)

    if status in (401, 403):
        return {"success": False, "status_code": status, "data": None, "results": [], "error": "鉴权失败，请检查 API Key 与权限"}
    if status == 429:
        return {"success": False, "status_code": status, "data": None, "results": [], "error": "速率限制触发（429），请稍后重试"}
    if status is None:
        return {"success": False, "status_code": None, "data": None, "results": [], "error": "无效响应"}

    if status == 204:
        return {"success": True, "status_code": status, "data": None, "results": [], "error": None}

    parsed = None
    text = ""
    try:
        parsed = resp.json()
    except ValueError:
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        parsed = None
    except Exception:
        parsed = None

    if 400 <= status < 600 and not (200 <= status < 300):
        if isinstance(parsed, dict):
            message = parsed.get("status_message") or parsed.get("error") or parsed.get("message") or str(parsed)
            data_field = parsed
        else:
            message = text or f"HTTP {status}"
            data_field = text or None
        return {"success": False, "status_code": status, "data": data_field, "results": [], "error": message}

    data = parsed if parsed is not None else (text or None)
    results = []
    if isinstance(data, dict):
        results = data.get("results") or data.get("data") or []
        if not isinstance(results, list):
            results = []
    elif isinstance(data, list):
        results = data
    else:
        results = []

    return {"success": True, "status_code": status, "data": data, "results": results, "error": None}