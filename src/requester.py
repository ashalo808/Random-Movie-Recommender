import logging
from typing import Optional
from src.api_client import ApiClient, ApiError

logger = logging.getLogger(__name__)

class Requester:
    def __init__(self, client: ApiClient):
        if not isinstance(client, ApiClient):
            raise ValueError("client must be an ApiClient instance")
        self.client = client

    def fetch_popular(self, page: int = 1) -> dict:
        # 添加输入验证
        if not isinstance(page, int) or page <= 0:
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "page 必须为正整数"}
        
        try:
            result = self.client.get_movies("movie/popular", {"page": page})
        except ApiError as e:
            result = {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}
        
        # 如果 ApiClient 返回失败且状态码表示限流或服务器错误，调整提示文本
        if not result.get("success"):
            status_code = result.get("status_code")
            if status_code == 429:
                result["error"] = "请求过于频繁，请稍后再试"
            elif status_code is not None and 500 <= status_code < 600:
                result["error"] = "服务器暂时不可用，请稍后再试"
        
        return result

    def discover_movies(self, params: dict | None = None) -> dict:
        # 添加输入验证
        if params is not None and not isinstance(params, dict):
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "params 必须为字典或 None"}
        
        try:
            result = self.client.discover_movies(params or {})
        except ApiError as e:
            result = {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}
        
        if not result.get("success"):
            status_code = result.get("status_code")
            if status_code == 429:
                result["error"] = "请求过于频繁，请稍后再试"
            elif status_code is not None and 500 <= status_code < 600:
                result["error"] = "服务器暂时不可用，请稍后再试"
        
        return result

    def search_movies(self, query: str, page: int = 1) -> dict:
        # 添加输入验证
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "query 不能为空"}
        if not isinstance(page, int) or page <= 0:
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "page 必须为正整数"}
        
        try:
            result = self.client.get_movies("search/movie", {"query": query.strip(), "page": page})
        except ApiError as e:
            result = {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}
        
        if not result.get("success"):
            status_code = result.get("status_code")
            if status_code == 429:
                result["error"] = "请求过于频繁，请稍后再试"
            elif status_code is not None and 500 <= status_code < 600:
                result["error"] = "服务器暂时不可用，请稍后再试"
        
        return result

    def get_movie_details(self, movie_id: int) -> dict:
        # 添加输入验证
        if not isinstance(movie_id, int) or movie_id <= 0:
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "movie_id 必须为正整数"}
        
        try:
            result = self.client.get_movies(f"movie/{movie_id}", {})
        except ApiError as e:
            result = {"success": False, "status_code": None, "data": None, "results": [], "error": str(e)}
        
        if not result.get("success"):
            status_code = result.get("status_code")
            if status_code == 429:
                result["error"] = "请求过于频繁，请稍后再试"
            elif status_code is not None and 500 <= status_code < 600:
                result["error"] = "服务器暂时不可用，请稍后再试"
        
        return result