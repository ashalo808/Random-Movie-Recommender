import time
import random
import logging
from typing import Optional
import requests.adapters

logger = logging.getLogger(__name__)

try:
    from urllib3.util.retry import Retry  # 常见位置
except Exception:
    Retry = None  # 在 create_retry 中会抛出更明确的错误

def create_retry(total: int = 3, backoff_factor: float = 0.3, status_forcelist: list | None = None, allowed_methods: frozenset | None = None, respect_retry_after_header: bool = True):
    """
    构造并返回兼容不同 urllib3 版本的 Retry 对象。

    参数:
        total (int): 总重试次数（非负）。
        backoff_factor (float): 回退因子。
        status_forcelist (list|None): 触发重试的 HTTP 状态码列表。
        allowed_methods (frozenset|None): 可被重试的 HTTP 方法集合。
        respect_retry_after_header (bool): 是否尊重 Retry-After 头。

    返回:
        Retry: urllib3.retry.Retry 实例（若构造失败，抛出异常以便调用方处理）。
    """
    if Retry is None:
        raise RuntimeError("urllib3 Retry not available (无法导入 urllib3.util.retry.Retry)")

    status_forcelist = status_forcelist if status_forcelist is not None else [429, 500, 502, 503, 504]

    # 尝试使用新参数名 allowed_methods；若抛 TypeError 则回退到老参数 method_whitelist
    kwargs = {
        "total": int(total),
        "backoff_factor": float(backoff_factor),
        "status_forcelist": list(status_forcelist),
        "respect_retry_after_header": bool(respect_retry_after_header),
    }
    if allowed_methods is not None:
        kwargs["allowed_methods"] = set(allowed_methods)

    try:
        return Retry(**kwargs)
    except TypeError:
        # 兼容老版本 urllib3 使用 method_whitelist 参数名
        if "allowed_methods" in kwargs:
            kwargs.pop("allowed_methods", None)
            kwargs["method_whitelist"] = set(allowed_methods)
        return Retry(**kwargs)

def apply_retry_to_session(session, retry):
    """
    将 Retry 策略包装到 HTTPAdapter 并 mount 到给定 session 的 http/https。

    参数:
        session: requests.Session 实例。
        retry: 由 create_retry 返回的 Retry 对象。

    返回:
        None

    行为:
        在失败时记录日志，但不抛出异常（由上层决定是否回滚或失败）。
    """
    try:
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logger.debug("已将 Retry 策略应用到 session（http/https）")
    except Exception as e:
        logger.warning("apply_retry_to_session: 无法将 Retry 策略应用到 session: %s", e)
        
def manual_retry_call(fn, attempts: int = 3, backoff_factor: float = 0.3, max_backoff: float = 10.0, jitter: float = 0.1, retry_on_exceptions=(Exception,), logger=logger):
    """
    在 urllib3 Retry 不可用时的回退重试器（通用包装）。
    - attempts: 最大尝试次数（>=1）
    - backoff_factor: 指数退避基数
    - max_backoff: 单次等待上限（秒）
    - jitter: 在等待时间上加减的随机比例（0..1）
    - retry_on_exceptions: 要重试的异常类型元组
    """
    if attempts < 1:
        attempts = 1
    last_exc = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except retry_on_exceptions as e:
            last_exc = e
            if i >= attempts:
                logger.debug("manual_retry_call: 已达最大重试次数 %d", attempts)
                break
            # 指数退避 + jitter
            sleep_sec = min(max_backoff, backoff_factor * (2 ** (i - 1)))
            jitter_amt = sleep_sec * jitter * (random.random() * 2 - 1)
            to_sleep = max(0.0, sleep_sec + jitter_amt)
            logger.debug("manual_retry_call: 第 %d 次失败，等待 %.2fs 后重试（error=%s）", i, to_sleep, e)
            time.sleep(to_sleep)
    # 重试用尽，抛出最后一个异常
    raise last_exc