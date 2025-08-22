# 工具函数模块
"""
通用工具函数
包含格式化输出、数据验证等可复用的小功能
"""
from typing import Dict, Any, Optional, Tuple


def validate_api_key(key: str | None) -> bool:
    """
    简单校验 API Key 的存在性与基本格式（非空字符串）。

    参数:
        key (str|None): 待校验的 key。

    返回:
        bool: 合法返回 True，否则 False。
    """
    if not isinstance(key, str):
        return False
    k = key.strip()
    if not k:
        return False
    if len(k) < 6:
        return False
    return True

def format_movie(movie: dict) -> str:
    """
    将 movie dict 格式化为用于展示的简短文本（包含 title, year, 简短概述）。

    参数:
        movie (dict): 电影信息字典。

    返回:
        str: 一行或多行的展示字符串（适合打印或日志）。
    """
    if not isinstance(movie, dict):
        return "<无效电影数据>"

    title = movie.get("title") or movie.get("original_title") or "<未知片名>"
    release = movie.get("release_date") or movie.get("first_air_date") or ""
    year = ""
    if isinstance(release, str) and release:
        year = release.split("-")[0]

    era = movie.get("_era") or ""

    rating = movie.get("vote_average")
    rating_str = f"{rating:.1f}" if isinstance(rating, (int, float)) else "N/A"
    vote_count = movie.get("vote_count") or movie.get("vote_count", None)
    vote_str = str(vote_count) if vote_count is not None else "N/A"

    genres = movie.get("genre_names") or movie.get("genres") or []
    genres_list = []
    if isinstance(genres, list):
        for g in genres:
            if isinstance(g, str):
                genres_list.append(g)
            elif isinstance(g, dict) and g.get("name"):
                genres_list.append(g.get("name"))
    genres_str = ", ".join(genres_list) if genres_list else ""

    overview = (movie.get("overview") or "").strip()

    def _truncate(text: str, max_len: int = 140) -> str:
        if not text:
            return "（暂无简介）"
        if len(text) <= max_len:
            return text
        return text[: max_len - 1].rstrip() + "…"

    overview = _truncate(overview, 140)

    header_parts = [f"🎬 {title}"]
    if year:
        header_parts.append(f"({year})")
    if era:
        header_parts.append(f"[{era}]")
    header_line = " ".join(header_parts)

    meta_parts = [f"⭐ {rating_str}", f"🗳️ {vote_str}"]
    if genres_str:
        meta_parts.append(f"🏷️ {genres_str}")
    meta_line = " · ".join(meta_parts)

    return f"{header_line}\n{meta_line}\n\n📝 {overview}"

def ensure_positive_int(value, name: str = "value") -> Tuple[bool, Optional[int], Optional[str]]:
    """
    验证输入可转换为正整数并返回结果、整数值与错误信息。

    返回:
        (ok: bool, int_value: int|None, error: str|None)
    """
    if value is None:
        return False, None, f"{name} 不能为空"
    try:
        iv = int(value)
    except (ValueError, TypeError):
        return False, None, f"{name} 必须是整数"
    if iv <= 0:
        return False, None, f"{name} 必须是正整数 (>0)"
    return True, iv, None