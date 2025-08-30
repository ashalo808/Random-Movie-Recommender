import os
import time
import random
import requests
import logging
from typing import Optional, Dict, Any, Tuple

from src.retry_policy import create_retry, apply_retry_to_session  # 保留对现有 retry_policy 的兼容调用

# 模块级 logger（保留现有 error.log 配置，但不重复 basicConfig 如果项目其他处已配置）
logger = logging.getLogger(__name__)

class ApiError(Exception):
    """API 层统一异常（用于可选抛出给上层）"""
    pass

class ApiClient:
    """
    改进说明（兼容原有接口）：
     - 支持指数退避 + 抖动的手动重试（在 urllib3 Retry 无法应用时回退）。
     - 暴露简单 metrics（requests/retries/failures）。
     - 可通过 env 或构造参数配置：max_retries, backoff_base, max_backoff, raise_on_failure, timeout, key_type。
     - 返回结构保持与原来一致的 dict 结构；当 raise_on_failure=True 时在最终失败抛出 ApiError。
    """
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        key_type: str = "v4",
        timeout: int = 30,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        max_backoff: Optional[float] = None,
        raise_on_failure: Optional[bool] = None,
    ):
        # 参数基本校验（保守）
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if api_key is None:
            api_key = os.getenv("TMDB_API_KEY", "")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if key_type not in ("v3", "v4"):
            raise ValueError("key_type must be 'v3' or 'v4'")
        if not (isinstance(timeout, int) and timeout > 0):
            raise ValueError("timeout must be a positive number")

        # 保存配置（规范 base_url）
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.key_type = key_type
        self.timeout = timeout

        # 可通过环境变量覆盖默认配置（传入参数优先）
        self.max_retries = int(max_retries if max_retries is not None else os.getenv("API_CLIENT_MAX_RETRIES", 3))
        self.backoff_base = float(backoff_base if backoff_base is not None else os.getenv("API_CLIENT_BACKOFF_BASE", 0.5))
        self.max_backoff = float(max_backoff if max_backoff is not None else os.getenv("API_CLIENT_MAX_BACKOFF", 60.0))
        self.raise_on_failure = bool(raise_on_failure if raise_on_failure is not None else (os.getenv("API_CLIENT_RAISE_ON_FAILURE", "1") == "1"))

        # 简单 metrics 收集
        self.metrics = {"requests": 0, "retries": 0, "failures": 0}

        # 创建 Session，尝试应用 urllib3 Retry（若成功则依赖 adapter 来重试；若失败，使用手动重试实现）
        self.session = requests.Session()
        self._use_manual_retry = False
        try:
            retry_obj = create_retry(total=self.max_retries,
                                     backoff_factor=0.3,
                                     status_forcelist=[429, 500, 502, 503, 504],
                                     allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "POST"}),
                                     respect_retry_after_header=True)
            apply_retry_to_session(self.session, retry_obj)
            self._use_manual_retry = False
            logger.info("ApiClient: 已为 session 应用 urllib3 Retry（max_retries=%d）", self.max_retries)
        except Exception as e:
            logger.warning("ApiClient: 无法应用 urllib3 Retry，启用手动重试回退：%s", e)
            self._use_manual_retry = True

        # 默认 headers / params
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        if self.key_type == "v4":
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            # v4 不使用 query api_key
            self.session.params = {}
        else:
            # v3 使用 query param api_key
            self.session.headers.pop("Authorization", None)
            self.session.params = {"api_key": self.api_key}

    def _build_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _safe_parse_json(self, resp: requests.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return None

    def _perform_request(self, method: str, path: str, params: dict | None = None, json: dict | None = None, headers: dict | None = None, timeout: Optional[int] = None) -> dict:
        """
        统一请求入口：返回结构化 dict：
         {"success": bool, "status_code": int|None, "data": dict|None, "results": list, "error": str|None}

        行为细节：
         - 优先使用已配置的 session（如果 urllib3 Retry 可用，则 session adapter 会自动重试）。
         - 如果启用手动重试（_use_manual_retry=True），使用内部实现的指数退避 + 抖动策略并更新 metrics["retries"]。
         - 最终失败根据 raise_on_failure 决定是返回 error 字段还是抛出 ApiError。
        """
        url = self._build_url(path)
        effective_timeout = timeout or self.timeout

        # 合并 headers（不修改 session.headers）
        req_headers = {}
        req_headers.update(self.session.headers or {})
        if isinstance(headers, dict):
            req_headers.update(headers)

        # 合并 params（不修改 session.params）
        merged_params = {}
        sess_params = getattr(self.session, "params", None)
        if isinstance(sess_params, dict):
            merged_params.update(sess_params)
        if isinstance(params, dict):
            merged_params.update(params)

        # 计数一次外部请求调用（不代表内部重试次数）
        self.metrics["requests"] += 1

        def single_request() -> Tuple[requests.Response | None, Exception | None]:
            try:
                resp = self.session.request(method, url, params=merged_params, json=json, headers=req_headers, timeout=effective_timeout)
                return resp, None
            except Exception as ex:
                return None, ex

        # 若 session 已经应用 urllib3 Retry，则直接调用一次（adapter 会内部重试）
        if not self._use_manual_retry:
            resp, exc = single_request()
            if exc is not None:
                # 网络层异常
                self.metrics["failures"] += 1
                msg = f"请求网络异常: {exc}"
                logger.warning(msg)
                if self.raise_on_failure:
                    raise ApiError(msg) from exc
                return {"success": False, "status_code": None, "data": None, "results": [], "error": msg}
            if not isinstance(resp, requests.Response):
                self.metrics["failures"] += 1
                msg = "invalid response"
                logger.warning(msg)
                if self.raise_on_failure:
                    raise ApiError(msg)
                return {"success": False, "status_code": None, "data": None, "results": [], "error": msg}

            status = resp.status_code
            data = self._safe_parse_json(resp)
            results = []
            if isinstance(data, dict):
                results = data.get("results") or data.get("data") or []
            success = 200 <= status < 300
            error = None if success else (data or resp.text)

            if not success:
                self.metrics["failures"] += 1
                # 对 429/5xx 给出友好提示文本（上层也可检测 status_code）
                if status == 429:
                    friendly = "请求被限流 (429)，请稍后重试或降低请求速率。"
                    if isinstance(error, dict):
                        # 尝试附加服务器信息
                        error = f"{friendly} details: {error}"
                    else:
                        error = f"{friendly} details: {error}"
                    logger.warning("Limit/429 on %s", url)
                elif 500 <= status < 600:
                    friendly = "服务器错误，请稍后重试。"
                    error = f"{friendly} details: {error}"
                    logger.warning("Server error %s on %s", status, url)
                if self.raise_on_failure:
                    raise ApiError(f"HTTP {status}: {error}")
            return {"success": success, "status_code": status, "data": data, "results": results, "error": error}

        # 手动重试逻辑（当 urllib3 Retry 不可用时）
        attempts = 0
        last_exc = None
        max_attempts = max(1, self.max_retries + 1)
        while attempts < max_attempts:
            attempts += 1
            resp, exc = single_request()
            if exc is not None:
                last_exc = exc
                # 如果还有重试机会，sleep 并继续
                if attempts < max_attempts:
                    self.metrics["retries"] += 1
                    backoff = min(self.max_backoff, self.backoff_base * (2 ** (attempts - 1)))
                    jitter = random.uniform(0, backoff * 0.2)
                    sleep_time = backoff + jitter
                    logger.warning("Network error for %s: %s — retry %s/%s after %.2fs", url, exc, attempts, max_attempts, sleep_time)
                    time.sleep(sleep_time)
                    continue
                else:
                    # 最终失败
                    self.metrics["failures"] += 1
                    msg = f"网络请求失败 after {attempts} attempts: {exc}"
                    logger.error(msg)
                    if self.raise_on_failure:
                        raise ApiError(msg) from exc
                    return {"success": False, "status_code": None, "data": None, "results": [], "error": msg}

            # got response
            if not isinstance(resp, requests.Response):
                self.metrics["failures"] += 1
                msg = "invalid response"
                logger.error(msg)
                if self.raise_on_failure:
                    raise ApiError(msg)
                return {"success": False, "status_code": None, "data": None, "results": [], "error": msg}

            status = resp.status_code
            data = self._safe_parse_json(resp)
            results = []
            if isinstance(data, dict):
                results = data.get("results") or data.get("data") or []
            success = 200 <= status < 300
            error = None if success else (data or resp.text)

            # 在 429 或 5xx 时进行重试（如果还有机会）
            if not success and (status == 429 or 500 <= status < 600):
                if attempts < max_attempts:
                    self.metrics["retries"] += 1
                    # honor Retry-After header if present (seconds)
                    retry_after = None
                    try:
                        retry_after = int(resp.headers.get("Retry-After")) if resp.headers.get("Retry-After") else None
                    except Exception:
                        retry_after = None
                    if retry_after and retry_after > 0:
                        sleep_time = min(self.max_backoff, retry_after)
                    else:
                        backoff = min(self.max_backoff, self.backoff_base * (2 ** (attempts - 1)))
                        jitter = random.uniform(0, backoff * 0.2)
                        sleep_time = backoff + jitter
                    logger.warning("Request %s returned %s; retry %s/%s after %.2fs", url, status, attempts, max_attempts, sleep_time)
                    time.sleep(sleep_time)
                    continue
                else:
                    self.metrics["failures"] += 1
                    msg = f"请求在 {attempts} 次尝试后以状态 {status} 失败"
                    logger.error(msg)
                    if self.raise_on_failure:
                        raise ApiError(msg)
                    # 给出更友好的错误信息
                    friendly = "请求被限流(429)或服务器错误(5xx)，请稍后再试。" if status == 429 or (500 <= status < 600) else str(error)
                    return {"success": False, "status_code": status, "data": data, "results": results, "error": friendly}

            # 非重试场景或成功时直接返回
            if not success:
                self.metrics["failures"] += 1
            return {"success": success, "status_code": status, "data": data, "results": results, "error": error}

    # 公开的便利方法（保留原有方法签名和行为）
    def get_movies(self, endpoint: str, params: dict | None = None) -> dict:
        if not isinstance(endpoint, str) or not endpoint.strip():
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "endpoint a non-empty string"}
        rel = endpoint.strip().lstrip("/")
        # 合并 params：不修改原始对象
        merged_params = {}
        sess_params = getattr(self.session, "params", None)
        if isinstance(sess_params, dict):
            merged_params.update(sess_params)
        if isinstance(params, dict):
            merged_params.update(params)
        return self._perform_request("GET", rel, params=merged_params)
    
    def get_genres(self, language: str = "en-US") -> dict:
        """获取电影类型列表"""
        return self.get_movies("genre/movie/list", {"language": language})

    def fetch_popular(self, page: int = 1) -> dict:
        if not isinstance(page, int) or page <= 0:
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "page 必须为正整数"}
        params = {"page": page}
        return self.get_movies("movie/popular", params)

    def discover_movies(self, params: dict = None) -> dict:
        query_params = params or {}
        return self.get_movies("discover/movie", query_params)

    def search_movies(self, query: str, page: int = 1) -> dict:
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "query 不能为空"}
        if not isinstance(page, int) or page <= 0:
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "page 必须为正整数"}
        return self.get_movies("search/movie", {"query": query.strip(), "page": page})

    def get_movie_details(self, movie_id: int) -> dict:
        if not isinstance(movie_id, int) or movie_id <= 0:
            return {"success": False, "status_code": None, "data": None, "error": "movie_id 必须为正整数"}
        rel = f"movie/{movie_id}".lstrip("/")
        result = self._perform_request("GET", rel, params=None, json=None, headers=None, timeout=self.timeout)
        if not result.get("success"):
            sc = result.get("status_code")
            if sc in (401, 403):
                result["error"] = "鉴权失败，请检查 API Key 和权限"
            elif sc == 404:
                result["error"] = "影片未找到"
        return result

    def get_metrics(self) -> Dict[str, int]:
        """返回当前 metrics 快照（requests/retries/failures）"""
        return dict(self.metrics)