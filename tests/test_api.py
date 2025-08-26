from pathlib import Path
import sys
# 将项目根（tests 的父目录）加入模块搜索路径，确保能 import config 等顶层模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import json
import logging
from config import get_tmdb_key
from src.api_client import ApiClient

logging.basicConfig(level=logging.INFO)

def pretty_print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def main():
    # 优先使用环境变量，回退到 config 中的常量（仅用于本地测试）
    api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
    if not api_key:
        print("未配置 TMDB_API_KEY。请通过环境变量或 config.get_tmdb_key 提供 API Key。")
        return

    client = ApiClient(base_url="https://api.themoviedb.org/3", api_key=api_key, key_type="v3", timeout=10, max_retries=2)

    print("=== fetch_popular page=1 ===")
    pretty_print(client.fetch_popular(1))

    print("\n=== search_movies 'inception' ===")
    pretty_print(client.search_movies("inception", page=1))

    print("\n=== get_movie_details id=550 ===")
    pretty_print(client.get_movie_details(550))

if __name__ == "__main__":
    main()