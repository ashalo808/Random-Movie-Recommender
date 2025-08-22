POPULAR = "movie/popular"
SEARCH = "search/movie"

def make_endpoint(path: str) -> str:
    """
    规范化并返回相对 endpoint 路径（剔除多余的斜杠、查询与片段）。

    行为：
      - 接受类似 "/movie/popular", "///search/movie?query=xx", "search//movie" 的输入
      - 去除前后空白与前后斜杠，压缩连续斜杠为单个斜杠
      - 移除查询字符串（?）和片段（#）部分
      - 若规范化后为空或包含空白字符，则抛出 ValueError

    参数:
        path (str): 原始路径字符串

    返回:
        str: 规范化后的相对路径（不以 '/' 开头，例如 "movie/popular"）

    抛出:
        TypeError: 当 path 不是 str 时
        ValueError: 当规范化后为空或包含非法空白字符时
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")

    s = path.strip()
    if not s:
        raise ValueError("empty endpoint path")

    # 移除查询字符串与片段
    for sep in ("?", "#"):
        if sep in s:
            s = s.split(sep, 1)[0]

    # 去掉首尾斜杠并压缩连续斜杠
    parts = [p for p in s.strip("/").split("/") if p != ""]
    if not parts:
        raise ValueError("empty endpoint after normalization")

    normalized = "/".join(parts)

    # 禁止包含空白字符（包括空格、制表符等）
    if any(c.isspace() for c in normalized):
        raise ValueError("endpoint contains whitespace")

    return normalized