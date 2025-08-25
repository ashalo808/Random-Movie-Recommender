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
    将 movie dict 格式化为用于展示的简短文本（包含 id, title, year, rating, genres, 简短概述）。
    - 对无效输入返回中文占位："<无效电影数据>"
    - 评分使用中文标签 "评分: ..."，投票数保留图标表示
    - overview 裁剪到最大 140 字符（含省略号）

    参数:
        movie (dict): 电影信息字典。

    返回:
        str: 一行或多行的展示字符串（适合打印或日志）。
    """
    if not isinstance(movie, dict):
        return "<无效电影数据>"

    title = movie.get("title") or movie.get("original_title") or "<未知片名>"
    mid = movie.get("id") or movie.get("movie_id")
    rd = movie.get("release_date") or movie.get("first_air_date") or ""
    year = None
    if isinstance(rd, str) and rd:
        parts = rd.split("-")
        if parts and parts[0].isdigit():
            year = parts[0]
    era = movie.get("_era") or ""
    rating = movie.get("vote_average") or movie.get("rating")
    votes = movie.get("vote_count") or movie.get("votes") or 0
    rating_str = f"{float(rating):.1f}" if isinstance(rating, (int, float)) else "N/A"
    vote_str = str(votes)

    # genres: 优先使用预填充的 genre_names，否则从 genres 字段回退
    genres_str = ""
    gnames = movie.get("genre_names")
    if isinstance(gnames, (list, tuple)) and gnames:
        genres_str = ", ".join([str(x) for x in gnames if x])
    else:
        gf = movie.get("genres") or []
        if isinstance(gf, list) and gf:
            names = []
            for g in gf:
                if isinstance(g, dict) and g.get("name"):
                    names.append(g.get("name"))
            if names:
                genres_str = ", ".join(names)

    # 简短概述裁剪：总行长度（包含前缀 "📝 "）不超过 140 字符
    overview = movie.get("overview") or ""
    if not isinstance(overview, str):
        overview = str(overview)
    line_prefix = "📝 "
    max_line_len = 140

    # 首次尝试按可用内容长度裁剪并保留省略号（如果可能）
    max_content_len = max_line_len - len(line_prefix)
    if max_content_len < 0:
        max_content_len = 0

    if len(overview) > max_content_len:
        if max_content_len > 3:
            overview = overview[: max_content_len - 3].rstrip() + "..."
        else:
            overview = overview[:max_content_len].rstrip()

    # 最终保证：拼接后的整行长度不超过 max_line_len（防止 emoji 等导致的计数差异）
    final_line = line_prefix + overview
    if len(final_line) > max_line_len:
        # 直接按字符数强制裁剪（不再追加省略号以保证长度）
        allowed = max_line_len - len(line_prefix)
        if allowed < 0:
            allowed = 0
        overview = overview[:allowed].rstrip()
    
    # 构建 header_line 和 meta_line
    header_parts = [f"🎬 {title}"]
    if mid is not None:
        header_parts.append(f"[id:{mid}]")
    if year:
        header_parts.append(f"({year})")
    if era:
        header_parts.append(f"[{era}]")
    header_line = " ".join(header_parts)

    # 使用中文标签：评分 与 类型（满足测试断言）
    meta_parts = [f"评分: {rating_str}", f"🗳️ {vote_str}"]
    if genres_str:
        meta_parts.append(f"类型: {genres_str}")
    meta_line = " · ".join(meta_parts)
    
    return f"{header_line}\n{meta_line}\n\n{line_prefix}{overview}"

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

# 新增：从 ApiClient 获取 genre 列表并构建 name->id 映射
def get_genre_map(client, language: str = "zh-CN") -> dict:
    """
    尝试从 client 获取电影类型列表并返回映射 {lower_name: id}。
    兼容多种返回结构，失败时返回空 dict。
    client 最优支持方法: client.get_genres(language) -> dict/list
    """
    try:
        # 优先使用 client.get_genres()
        if hasattr(client, "get_genres") and callable(getattr(client, "get_genres")):
            raw = client.get_genres(language)
        else:
            # 回退到直接 HTTP 请求，避免引入循环导入：在函数内导入 send_request 与 requests
            from src.requester import send_request
            import requests
            base = getattr(client, "base_url", "https://api.themoviedb.org/3")
            sess = getattr(client, "session", requests.Session())
            raw = send_request(sess, base, "GET", "genre/movie/list", params={"language": language})
        if not raw:
            return {}
        # 兼容结构 {"genres": [...]} 或直接 list
        genres = None
        if isinstance(raw, dict):
            genres = raw.get("genres") or (raw.get("data") and raw.get("data").get("genres"))
        elif isinstance(raw, list):
            genres = raw
        if not isinstance(genres, list):
            return {}
        mapping = {}
        for g in genres:
            if not isinstance(g, dict):
                continue
            gid = g.get("id")
            name = g.get("name") or g.get("english_name") or ""
            if gid and name:
                mapping[name.strip().lower()] = gid
        return mapping
    except Exception:
        return {}

# 按 genre_id 或 genre_name 在 movies 列表中做过滤，返回新列表（不修改传入对象）
def filter_by_genre(movies: list, genre_name: str = None, genre_id: int = None) -> list:
    """
    按优先级进行匹配并返回新的电影列表副本：
      1. 若提供 genre_id，则优先用 movie.get("genre_ids") 精确匹配；
      2. 否则若 movie 包含 "genres"（list of dict），按 name 精确或包含匹配；
      3. 否则在 title/overview 中做子串（忽略大小写）匹配；
    不改变原 movies 对象（返回浅拷贝的条目）。
    """
    if not movies:
        return []
    lname = genre_name.strip().lower() if isinstance(genre_name, str) and genre_name.strip() else None
    out = []
    for mv in movies:
        try:
            if not isinstance(mv, dict):
                continue
            matched = False
            if genre_id is not None:
                gids = mv.get("genre_ids") or []
                if isinstance(gids, (list, tuple)) and genre_id in gids:
                    matched = True
            if matched:
                out.append(dict(mv))
                continue
            if lname:
                # 先检查完整的 genres 字段
                gf = mv.get("genres") or []
                if isinstance(gf, list):
                    for g in gf:
                        if isinstance(g, dict):
                            gname = str(g.get("name") or "").strip().lower()
                            if gname and (lname == gname or lname in gname or gname in lname):
                                matched = True
                                break
                if matched:
                    out.append(dict(mv))
                    continue
                # 最后在 title/overview 中做子串匹配
                txt = " ".join([str(mv.get("title") or ""), str(mv.get("original_title") or ""), str(mv.get("overview") or "")]).lower()
                if lname and lname in txt:
                    out.append(dict(mv))
                    continue
        except Exception:
            continue
    return out