import os
import threading
import time
import logging
from typing import Optional, Dict, Any, Callable, Tuple, Union

from config import get_tmdb_key
from src.api_client import ApiClient

logger = logging.getLogger(__name__)

# 简单缓存：key -> ApiClient
_client_cache: Dict[Tuple[str, str, str, int, int, int, Tuple[Tuple[str, Any], ...]], ApiClient] = {}
_client_lock = threading.RLock()

def _freeze_for_key(obj):
    """将可变/嵌套结构转为可哈希的不可变表示（dict->tuple, list/tuple/set->tuple）。"""
    if isinstance(obj, dict):
        return tuple(sorted((str(k), _freeze_for_key(v)) for k, v in obj.items()))
    if isinstance(obj, (list, tuple, set)):
        return tuple(_freeze_for_key(v) for v in obj)
    try:
        hash(obj)
        return obj
    except Exception:
        return repr(obj)

def _make_cache_key(api_key: str, base_url: str, key_type: str, timeout: int, max_retries: int, pool_size: int, extra_opts: Optional[Dict[str, Any]] = None):
    extras = _freeze_for_key(extra_opts or {})
    return (str(api_key), base_url, key_type, int(timeout), int(max_retries), int(pool_size), extras)

def create_client(
    api_key: str | None = None,
    base_url: str = "https://api.themoviedb.org/3",
    key_type: str = "v3",
    timeout: int = 10,
    max_retries: int = 3,
    pool_size: int = 10,
    proxies: Optional[Dict[str, str]] = None,
    verify: Union[bool, str] = True,
    headers: Optional[Dict[str, str]] = None,
    session_factory: Optional[Callable[[], "requests.Session"]] = None,
    thread_safe_singleton: bool = True,
    reuse_cache: bool = True
) -> ApiClient:
    """
    创建并返回已配置的 ApiClient 实例。

    Args:
        api_key (str|None): TMDb API Key（可空，函数会尝试从环境或 config 获取）
        base_url (str): TMDb 基础 URL
        key_type (str): "v3" 或 "v4"
        timeout (int): 请求超时（秒，>0）
        max_retries (int): 重试次数（>=0）
        pool_size (int): 连接池大小建议值
        proxies (dict|None): 可选代理配置
        verify (bool|str): 证书验证参数
        headers (dict|None): 自定义请求头
        session_factory (callable|None): 可选的 requests.Session 构造器（用于依赖注入/测试）
        thread_safe_singleton (bool): 是否使用线程安全的单例缓存
        reuse_cache (bool): 是否复用缓存的客户端实例

    Returns:
        ApiClient: 已配置好的同步 ApiClient 实例

    Errors:
        若未提供 api_key 则抛出 ValueError；参数非法将由 ApiClient 的验证抛出 ValueError。
    """
    if api_key is None or not str(api_key).strip():
        api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
    if not api_key:
        raise ValueError("api_key required (请通过参数、环境变量 TMDB_API_KEY 或 config 提供)")

    key = _make_cache_key(api_key, base_url, key_type, timeout, max_retries, pool_size, {"proxies": proxies or {}, "verify": verify, "headers": headers or {}})

    if reuse_cache:
        lock = _client_lock if thread_safe_singleton else threading.Lock()
        with lock:
            client = _client_cache.get(key)
            if client:
                logger.debug("create_client: 返回缓存的 ApiClient")
                return client

    # 延迟导入 requests 以避免模块初始化问题
    import requests
    from requests.adapters import HTTPAdapter

    # 构造 ApiClient（参数校验在 ApiClient 中进行）
    client = ApiClient(base_url=base_url, api_key=str(api_key), key_type=key_type, timeout=int(timeout), max_retries=int(max_retries))

    # 若用户提供了自定义 session_factory，则使用之（便于测试/注入）
    if session_factory:
        try:
            session = session_factory()
            if hasattr(session, "headers") and isinstance(headers, dict):
                session.headers.update(headers)
            client.session = session
        except Exception as e:
            logger.warning("create_client: session_factory 失败，使用内部 session (%s)", e)

    # 否则按传入参数调整内部 session
    sess = getattr(client, "session", None)
    if sess is not None:
        try:
            # 代理、证书验证、头
            if proxies:
                sess.proxies.update(proxies)
            sess.verify = verify
            if headers:
                sess.headers.update(headers)

            # 使用 HTTPAdapter 调整连接池大小（pool_connections/pool_maxsize）
            try:
                adapter = HTTPAdapter(pool_connections=max(1, pool_size), pool_maxsize=max(1, pool_size))
                sess.mount("http://", adapter)
                sess.mount("https://", adapter)
            except Exception as e:
                logger.debug("create_client: 无法 mount HTTPAdapter，忽略 (%s)", e)
        except Exception as e:
            logger.debug("create_client: 配置 session 时出现问题，忽略 (%s)", e)

    # 缓存并返回
    if reuse_cache:
        with _client_lock:
            _client_cache[key] = client
    return client

def fetch_popular_quick(api_key: str, page: int = 1, **client_kwargs) -> dict:
    """
    便捷函数：创建（或复用）客户端并快速获取热门电影。

    Args:
        api_key (str): TMDb API Key
        page (int): 页码（默认为 1）
        **client_kwargs: 传入 create_client 的其余参数

    Returns:
        dict: 结构化结果，包含 "success", "status_code", "data", "results", "error" 等字段，
              并在成功或失败时附加 "_query_info"（包含 fetched_at、page 等调试信息）。

    Errors:
        捕获并返回异常信息到结果的 "error" 字段，而不会抛出到上层。
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    try:
        client = create_client(api_key, **client_kwargs)
        resp = client.fetch_popular(page)
        if isinstance(resp, dict):
            resp.setdefault("_query_info", {})
            resp["_query_info"].update({"fetched_at": ts, "page": page})
        return resp
    except Exception as e:
        logger.exception("fetch_popular_quick 失败")
        return {"success": False, "status_code": None, "data": None, "results": [], "error": str(e), "_query_info": {"fetched_at": ts, "page": page}}

def search_quick(api_key: str, query: str, page: int = 1, **client_kwargs) -> dict:
    """
    便捷函数：创建（或复用）客户端并执行电影搜索。

    Args:
        api_key (str): TMDb API Key
        query (str): 搜索关键词（不能为空）
        page (int): 页码（默认为 1）
        **client_kwargs: 传入 create_client 的其余参数

    Returns:
        dict: 结构化结果，包含 "success", "status_code", "data", "results", "error" 等字段，
              并在成功或失败时附加 "_query_info"（包含 fetched_at、query、page 等调试信息）。

    Errors:
        当 query 非法时直接返回带 error 的结果；其他异常会被捕获并写入 error 字段。
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    try:
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "status_code": None, "data": None, "results": [], "error": "query 不能为空", "_query_info": {"fetched_at": ts, "page": page}}
        client = create_client(api_key, **client_kwargs)
        resp = client.search_movies(query, page)
        if isinstance(resp, dict):
            resp.setdefault("_query_info", {})
            resp["_query_info"].update({"fetched_at": ts, "query": query, "page": page})
        return resp
    except Exception as e:
        logger.exception("search_quick 失败")
        return {"success": False, "status_code": None, "data": None, "results": [], "error": str(e), "_query_info": {"fetched_at": ts, "query": query, "page": page}}

def create_async_client(
    api_key: str | None = None,
    base_url: str = "https://api.themoviedb.org/3",
    key_type: str = "v3",
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
    **kwargs
):
    """
    创建异步客户端（基于 aiohttp）。

    Args:
        api_key (str|None): TMDb API Key（可空，函数会尝试从环境或 config 获取）
        base_url (str): TMDb 基础 URL
        key_type (str): "v3" 或 "v4"
        headers (dict|None): 自定义请求头
        timeout (int): 请求超时（秒）
        **kwargs: 额外 aiohttp/连接参数（如 pool_size、verify、trust_env 等）

    Returns:
        aiohttp.ClientSession: 已配置的异步会话（若 aiohttp 可用）

    Errors:
        若未安装 aiohttp 则抛出 RuntimeError；若未提供 api_key 则抛出 ValueError。
    """
    try:
        import aiohttp
    except Exception:
        raise RuntimeError("aiohttp 未安装，无法创建异步客户端")

    if api_key is None or not str(api_key).strip():
        api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
    if not api_key:
        raise ValueError("api_key required (请通过参数、环境变量 TMDB_API_KEY 或 config 提供)")

    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if key_type == "v4":
        hdrs["Authorization"] = f"Bearer {api_key}"

    conn = aiohttp.TCPConnector(limit_per_host=kwargs.get("pool_size", 10), ssl=kwargs.get("verify", True))
    session = aiohttp.ClientSession(base_url=base_url.rstrip("/"), headers=hdrs, connector=conn, trust_env=kwargs.get("trust_env", True))
    return session