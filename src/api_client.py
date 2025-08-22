# 导入必要的库
import requests
import logging
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from src.retry_policy import create_retry, apply_retry_to_session, manual_retry_call
from typing import Optional, Dict, Any

# 配置日志
logging.basicConfig(
    filename='error.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# 模块级 logger，避免 NameError
logger = logging.getLogger(__name__)

# 初始化 API 客户端，保存配置并创建带重试策略的 requests.Session
class ApiClient:
    def __init__(self, base_url: str, api_key: str, key_type: str = "v3", timeout: int= 10, max_retries: int = 3):
        """
        初始化 API 客户端，保存配置并创建带重试策略的 requests.Session
        
        Args:
            base_url (str): TMDb 基础 URL
            api_key (str): 密钥
            key_type (str): "v3" or "v4"
            timeout (int): 秒（>0）
            max_retries (int): 重试次数（>=0）
            
        Returns:
            None 
            
        Errors:
            非法参数会抛出 ValueError
        """
        # 参数校验 (非法参数抛出 ValueError)
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if key_type not in ("v3", "v4"):
            raise ValueError("key_type must be 'v3' or 'v4'")
        if not (isinstance(timeout, int) and timeout > 0):
            raise ValueError("timeout must be a positive number")
        if not (isinstance(max_retries, int) and max_retries >= 0):
            raise ValueError("max_retries must be a non-negative integer")
         
        # 保存配置（规范 base_url）
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.key_type = key_type
        self.timeout = float(timeout)
        self.max_retries = max_retries

        # 创建 Session
        self.session = requests.Session()
        
        # 尝试应用 urllib3 Retry 策略；若失败则标记使用手动重试
        try:
            retry_obj = create_retry(total=self.max_retries,
                                     backoff_factor=0.3,
                                     status_forcelist=[429, 500, 502, 503, 504],
                                     allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
                                     respect_retry_after_header=True)
            apply_retry_to_session(self.session, retry_obj)
            self._use_manual_retry = False
            logger.info("ApiClient: 使用 urllib3 Retry 策略（max_retries=%d）", self.max_retries)
        except Exception as e:
            logger.warning("ApiClient: 无法使用 urllib3 Retry，启用手动重试回退：%s", e)
            self._use_manual_retry = True
        
        # 默认 Headers
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        
        # 根据 key_type 决定认证方式
        if self.key_type == "v4":
            # v4 使用 Bearer token
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            # 确保没有遗留的 query api_key
            self.session.params = {}
        else:
            # v3 常通过 query param api_key 认证
            self.session.headers.pop("Authorization", None)
            self.session.params = {"api_key": self.api_key}
            
        # 已通过 create_retry/apply_retry_to_session 应用重试策略
    
    def _perform_request(self, method: str, path: str, params: dict | None = None, json: dict | None = None, headers: dict | None = None, timeout: Optional[int] = None) -> dict:
        """
        统一发起请求的辅助函数，返回结构化 dict：
          {"success": bool, "status_code": int|None, "data": dict|None, "results": list, "error": str|None}
        会根据初始化时的策略使用 session（带 urllib3 Retry）或 manual_retry_call 回退重试。
        """
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        req_kwargs = {"params": params, "json": json, "headers": headers or {}, "timeout": timeout or self.timeout}

        def do_request():
            return self.session.request(method, url, **req_kwargs)

        # 执行请求（可能通过 manual_retry_call）
        try:
            if self._use_manual_retry:
                resp = manual_retry_call(lambda: do_request(), attempts=max(1, self.max_retries + 1), backoff_factor=0.3, max_backoff=10.0, jitter=0.2, retry_on_exceptions=(Exception,), logger=logger)
            else:
                resp = do_request()
        except Exception as e:
            logger.warning("请求失败: %s %s -> %s", method, url, e)
            return {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}

        # 处理 requests.Response
        if not isinstance(resp, requests.Response):
            logger.warning("请求返回非 Response 类型：%r", resp)
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "invalid response"}

        status = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = None

        results = []
        if isinstance(data, dict):
            # 兼容不同字段名
            results = data.get("results") or data.get("data") or []
        success = 200 <= status < 300
        error = None if success else (data or resp.text)

        return {"success": success, "status_code": status, "data": data, "results": results, "error": error}
    
    def get_movies(self, endpoint: str, params: dict | None = None) -> dict:
        """
        通用列表类接口调用：向给定 endpoint 发送 GET 请求并返回统一结构。

        Args:
            endpoint (str): TMDb API 的相对路径，例如 "movie/popular" 或 "search/movie"。
            params (dict | None): 查询参数字典。

        Returns:
            dict: 结构化结果（与 _send_request 相同），并在成功时保证:
                result["data"] 为原始解析 JSON（dict），
                result["results"] 为 data.get("results", [])（始终存在且为 list，便于上层直接使用）。

        Errors:
            若请求失败，返回的 "success" 为 False，"results" 为 []，"error" 包含简短错误描述。
        """
        # 校验 endpoint
        if not isinstance(endpoint, str) or not endpoint.strip():
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "results": [],
                "error": "endpoint a non-empty string"
            }
        
        # 规范化 endpoint，避免多余斜杠
        rel = endpoint.strip().lstrip("/")

        # 合并 params：不修改原始对象
        merged_params = {}
        sess_params = getattr(self.session, "params", None)
        if isinstance(sess_params, dict):
            merged_params.update(sess_params)
        if isinstance(params, dict):
            merged_params.update(params)

        # 统一走 _perform_request, 复用重试与响应处理逻辑
        return self._perform_request("GET", rel, params=merged_params)

    def fetch_popular(self, page: int = 1) -> dict:
        """
        获取热门电影的便捷方法。
        内部调用 get_movies("movie/popular", {"page": page}) 并返回结构化结果。
        保证在成功时返回的结果中有 "results"（list），失败时返回空列表并包含错误信息。

        Args:
            page (int): 页码（默认为 1）。

        Returns:
            dict: 结构化结果，典型键:
                {
                    "success": bool,
                    "status_code": int|None,
                    "data": dict|None,
                    "results": list,   # 成功时为电影列表，失败时为 []
                    "error": str|None
                }

        Errors:
            校验 page 必须为正整数；若非法则不发起请求，直接返回 error。
        """
        # 校验 page 必须为正整数
        if not isinstance(page, int) or page <= 0:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "results": [],
                "error": "page 必须为正整数"
            }
        params = {"page": page}
        # 修正：使用 get_movies 而非 _request
        return self.get_movies("movie/popular", params)
    
    def discover_movies(self, params: dict = None) -> dict:
        """
        使用 discover API 查询电影，支持丰富的过滤条件。
        常用参数:
            - primary_release_date.gte: "YYYY-MM-DD"
            - primary_release_date.lte: "YYYY-MM-DD"
            - sort_by: "popularity.desc", "vote_average.desc" 等
            - with_genres: 用逗号分隔的类型ID
            - vote_count.gte: 最低投票数
        """
        query_params = params or {}
        return self.get_movies("discover/movie", query_params)

    def search_movies(self, query: str, page: int = 1) -> dict:
        """
        搜索电影的便捷方法。
        内部调用 get_movies("search/movie", {"query": query, "page": page}) 并返回结构化结果。
        在调用前校验 query 非空。

        Args:
            query (str): 搜索关键词，不能为空。
            page (int): 页码（默认为 1）。

        Returns:
            dict: 结构化结果，包含 "results"（list），失败时 results 为空 list 且 error 有信息。

        Errors:
            若 query 为空或非字符串，立即返回 error 而不发起网络请求。
        """
        # 校验 query
        if not isinstance(query, str) or not query.strip():
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "results": [],
                "error": "query 不能为空"
            }
        # 校验 page
        if not isinstance(page, int) or page <= 0:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "results": [],
                "error": "page 必须为正整数"
            }
        return self.get_movies("search/movie", {"query": query.strip(), "page": page})

    def get_movie_details(self, movie_id: int) -> dict:
        """
        获取单部电影详细信息。
        调用 _send_request("GET", f"movie/{movie_id}")，返回单个电影对象或错误信息。
        对 404（未找到）给出友好提示；对鉴权失败给出明确信息。

        Args:
            movie_id (int): TMDb 分配的电影 ID（正整数）。

        Returns:
            dict: 结构化结果，典型键:
                {
                    "success": bool,
                    "status_code": int|None,
                    "data": dict|None,   # 成功时为单个电影的详细 dict
                    "error": str|None
                }

        Errors:
            校验 movie_id 为正整数；非法则直接返回 error。
        """
        # 校验 movie_id
        if not isinstance(movie_id, int) or movie_id <= 0:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": "movie_id 必须为正整数"
            }

        rel = f"movie/{movie_id}".lstrip("/")
        # 直接复用 _perform_request，返回结构化结果
        result = self._perform_request("GET", rel, params=None, json=None, headers=None, timeout=self.timeout)

        # 对 404 / 鉴权等情况，保证 error 信息友好
        if not result.get("success"):
            sc = result.get("status_code")
            if sc in (401, 403):
                result["error"] = "鉴权失败，请检查 API Key 和权限"
            elif sc == 404:
                result["error"] = "影片未找到"
        return result