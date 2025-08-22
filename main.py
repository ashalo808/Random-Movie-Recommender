#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Random Movie Recommender - 随机电影推荐器
主程序入口文件
"""
import os
import sys
import random
import logging
import requests
from datetime import datetime
from config import get_tmdb_key
from src import storage
from src.utils import format_movie, ensure_positive_int, validate_api_key
from src.requester import send_request
from src.endpoints import POPULAR, SEARCH, make_endpoint
from src.api_client import ApiClient
from src.recommenders import pick_random_movie, recommend_batch

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CACHE_DIR = "data"
CACHE_FILE = f"{CACHE_DIR}/movies_cache.json"
CACHE_TTL_SECONDS = 60 * 60  # 1 小时

def _extract_total_pages(resp: dict) -> int:
    """从响应中提取总页数，并限制最大页数为500"""
    if not isinstance(resp, dict):
        return 1
    d = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    tp = d.get("total_pages") if isinstance(d, dict) else None
    try:
        return max(1, min(int(tp) if tp is not None else 1, 500))
    except Exception:
        return 1

def _extract_total_pages(resp: dict) -> int:
    """从响应中提取总页数，并限制最大页数为500"""
    if not isinstance(resp, dict):
        return 1
    # 兼容不同结构：优先 data.total_pages，其次直接 total_pages，再退回 1
    d = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    tp = None
    if isinstance(d, dict):
        tp = d.get("total_pages") or d.get("totalPages") or d.get("total")
    if tp is None:
        # 兼容老结构或直接把 resp 当作包含 total_pages 的 dict
        tp = resp.get("total_pages") or resp.get("totalPages") or resp.get("total") if isinstance(resp, dict) else None
    try:
        tp_int = int(tp) if tp is not None else 1
    except Exception:
        tp_int = 1
    # TMDb API 最大页通常限制 500，保证返回范围合理
    return max(1, min(500, tp_int))


# 增加一个辅助函数来为电影打上年代标签
def _tag_movies_with_era(movies: list) -> list:
    """
    为每部 movie 添加 "_era" 字段，按上映年取年代（例如 1980s、1990s）。
    - 每部电影独立处理（不会把第一个的 era 误用到其它电影）。
    - 不修改传入对象（返回浅拷贝列表），避免副作用导致重复或缓存污染。
    """
    tagged = []
    for mv in (movies or []):
        try:
            # shallow copy，避免修改原始数据结构
            m = dict(mv) if isinstance(mv, dict) else {"title": str(mv)}
            rd = m.get("release_date") or m.get("first_air_date") or ""
            year = None
            if isinstance(rd, str) and rd:
                # 以 YYYY-... 形式解析年份
                parts = rd.split("-")
                if parts and parts[0].isdigit():
                    year = int(parts[0])
            era = ""
            if isinstance(year, int):
                if year < 1900:
                    era = "经典"
                else:
                    decade = (year // 10) * 10
                    era = f"{decade}s"
            m["_era"] = era
        except Exception:
            # 任何异常都要保证返回结构完整且不会抛出，避免刷新流程中断
            m = dict(mv) if isinstance(mv, dict) else {"title": str(mv)}
            m["_era"] = ""
        tagged.append(m)
    return tagged

def load_or_fetch(client: ApiClient, force_fetch: bool = False, max_random_page: int = 10) -> dict:
    """
    获取跨年代电影集合，返回 dict 且包含 "results"（list）。
    优先使用缓存，缓存格式同此函数返回值。
    """
    logging.info("🎬 正在准备电影数据...")
    # 尝试从缓存读取（要求为 dict 且包含 results）
    if not force_fetch and not storage.is_cache_expired(CACHE_FILE, CACHE_TTL_SECONDS):
        cached = storage.load_json(CACHE_FILE)
        if isinstance(cached, dict) and cached.get("results"):
            logging.info("✅ 缓存有效，从文件加载。")
            # 为结果打年代标签（若尚未打）
            cached["results"] = _tag_movies_with_era(cached.get("results", []))
            return cached
    # 缓存无效或强制刷新，从 API 获取多个年代的数据并合并
    logging.info("⏳ 缓存无效或强制刷新，正在从 TMDb 获取跨年代数据...")
    current_year = datetime.now().year
    era_ranges = [
        ("经典时代", 1950, 1975),
        ("黄金时代", 1976, 1989),
        ("现代早期", 1990, 2005),
        ("现代中期", 2006, 2015),
        ("现代近期", 2016, current_year)
    ]
    all_results = []
    era_info = []
    for era_name, start, end in era_ranges:
        year = random.randint(start, end)
        page = random.randint(1, max_random_page)
        params = {
            "primary_release_year": year,
            "page": page,
            "sort_by": "popularity.desc",
            "vote_count.gte": 50
        }
        logging.info("📡 查询 %s 年份 %d（页 %d）...", era_name, year, page)
        try:
            resp = client.discover_movies(params)
        except Exception as e:
            logging.warning("⚠️ TMDb 请求 %s 年代失败：%s", era_name, e)
            # fallback: 直接用 requester.send_request，通过 client.session 发起原始请求
            try:
                sess = getattr(client, "session", requests.Session())
                raw = send_request(sess, getattr(client, "base_url", "https://api.themoviedb.org/3"), "GET", "discover/movie", params=params)
                if raw.get("success"):
                    # 兼容原有 client.discover_movies 返回结构
                    resp = {"success": True, "results": raw.get("results") or [], "data": raw.get("data")}
                else:
                    logging.warning("requester fallback 失败: %s", raw.get("error"))
                    continue
            except Exception as e2:
                logging.warning("requester fallback 异常: %s", e2)
                continue
        if not isinstance(resp, dict) or not resp.get("success") or not resp.get("results"):
            logging.warning("⚠️ %s 年代无有效结果或请求失败，跳过。", era_name)
            continue
        results = resp.get("results", [])[:20]
        for m in results:
            # 标注年代标签，方便展示与调试
            if isinstance(m, dict):
                m["_era"] = era_name
        all_results.extend(results)
        era_info.append({"era": era_name, "years": f"{start}-{end}", "count": len(results)})
    if not all_results:
        logging.warning("⚠️ 未能从 API 获取到任何电影，尝试使用旧缓存（若有）")
        old = storage.load_json(CACHE_FILE)
        if isinstance(old, dict) and old.get("results"):
            old["results"] = _tag_movies_with_era(old.get("results", []))
            return old
        return {"success": False, "results": [], "error": "no data"}
    merged = {
        "success": True,
        "results": all_results,
        "_query_info": {
            "fetched_at": datetime.now().isoformat(),
            "era_info": era_info,
            "total": len(all_results)
        }
    }
    try:
        storage.save_json(CACHE_FILE, merged)
        logging.info("💾 已缓存 %d 部跨年代电影。", len(all_results))
    except Exception:
        logging.exception("保存缓存失败")
    return merged

def interactive_loop(client: ApiClient):
    print("✨ 随机电影推荐器 ✨")
    print("按回车随机推荐一部；输入 b 列出 3 个推荐；输入 r 回源刷新；输入 q 退出。\n")
    data = load_or_fetch(client, force_fetch=False)
    if not data:
        print("🚫 无数据可用（既无法从 API 获取也无缓存）。")
        return

    results = data.get("results") or []
    if not results:
        print("🔍 没有可推荐的影片。")
        return

    try:
        while True:
            cmd = input("按回车获取推荐 / b 批量 / r 刷新 / q 退出 > ").strip().lower()
            if cmd == "q":
                print("👋 再见！")
                return
            if cmd == "r":
                data = load_or_fetch(client, force_fetch=True)
                if not data:
                    print("⚠️ 刷新失败，仍使用旧缓存（若有）。")
                    data = storage.load_json(CACHE_FILE)
                results = (data.get("results") or []) if data else []
                if not results:
                    print("🔍 无可用结果。")
                    continue
            if not results:
                print("🔍 当前无可用影片。")
                continue

            if cmd == "b":
                # 批量推荐 - 平衡各指标权重
                prefs = {
                    "weights": {
                        "popularity": 0.3,
                        "rating": 0.3, 
                        "freshness": 0.4  # 增加新鲜度权重以引入更多不同年代的电影
                    },
                    "temperature": 3.0,   # 提高温度，让选择更随机
                    "temporal_balance": True,  # 启用年代平衡
                    "temporal_balance_strength": 1.5 # 提高年代平衡的强度，更大地惩罚热门年代
                }
                batch = recommend_batch(results, n=3, preferences=prefs, seed=None, diversify_by="genre")
                print("\n🎯 批量推荐：\n")
                for i, mv in enumerate(batch, 1):
                    era = mv.get("_era", "")
                    print(f"{i}. [{era}]")
                    print(format_movie(mv))
                    print("-" * 40)
                print()
                continue

            # 单个推荐 - 同样平衡各指标
            prefs = {
                "weights": {
                    "popularity": 0.3,
                    "rating": 0.3,
                    "freshness": 0.4 # 增加新鲜度权重
                },
                "temperature": 3.0,  # 更高温度，更随机
                "temporal_balance": True, # 启用年代平衡
                "temporal_balance_strength": 1.5 # 提高年代平衡的强度
            }
            chosen = pick_random_movie(results, preferences=prefs, seed=None)
            if not chosen:
                # 回退到简单随机
                chosen = random.choice(results)
            print("\n" + format_movie(chosen) + "\n")
    except KeyboardInterrupt:
        print("\n👋 已取消。")

def main():
    api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
    if not api_key:
        print("❗ 未配置 TMDB_API_KEY。请设置环境变量或在 config 中提供。")
        return
    client = ApiClient(base_url=os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3"),
                      api_key=api_key,
                      key_type=os.getenv("TMDB_KEY_TYPE", "v3"),
                      timeout=int(os.getenv("REQUEST_TIMEOUT", 30)),
                      max_retries=int(os.getenv("MAX_RETRIES", 2)))
    interactive_loop(client)

if __name__ == "__main__":
    main()