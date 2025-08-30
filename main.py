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
from src.utils import format_movie, ensure_positive_int, validate_api_key, get_genre_map, filter_by_genre
# 将 send_request 替换为 Requester，以便使用统一的错误/重试封装
from src.requester import Requester
from src.endpoints import POPULAR, SEARCH, make_endpoint
from src.api_client import ApiClient
from src.recommenders import pick_random_movie, recommend_batch
from src.preferences import (
    load_preferences, save_preferences, validate_preferences, 
    create_default_preferences_if_missing, DEFAULT_PREFERENCES
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CACHE_DIR = "data"
CACHE_FILE = f"{CACHE_DIR}/movies_cache.json"
CACHE_TTL_SECONDS = 60 * 60  # 1 小时

era_ranges = [
    ("1970s", 1970, 1979),
    ("1980s", 1980, 1989),
    ("1990s", 1990, 1999),
    ("2000s", 2000, 2009),
    ("2010s", 2010, 2019),
    ("2020s", 2020, datetime.now().year),
]

GENRE_ALIASES = {
    "科幻": "science fiction",
    "科幻片": "science fiction",
    "剧情": "drama",
    "喜剧": "comedy",
    "动作": "action",
    "惊悚": "thriller",
    "恐怖": "horror",
    "爱情": "romance",
    "纪录": "documentary",
    "动画": "animation",
    "冒险": "adventure",
    "犯罪": "crime",
    "家庭": "family",
    "奇幻": "fantasy",
    "音乐": "music",
    "历史": "history",
    "战争": "war",
    "西部": "western",
}

def _choose_genre_from_map(genre_map: dict):
    """
    从 genre_map(name->id) 中交互选择，返回 (name_lower, id) 或 (None,None)
    """
    if not genre_map:
        return None, None
    names = sorted(genre_map.keys())
    print("\n可用类型：")
    for i, n in enumerate(names, 1):
        print(f"{i}. {n}")
    print("输入编号选择，或输入名称；回车取消。")
    choice = input("选择> ").strip()
    if not choice:
        return None, None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(names):
            sel = names[idx - 1]
            return sel, genre_map.get(sel)
    low = choice.lower()
    for n in names:
        if n.lower() == low:
            return n, genre_map.get(n)
    for n in names:
        if low in n.lower():
            return n, genre_map.get(n)
    return None, None

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

def show_metrics(client: ApiClient) -> None:
    """展示 ApiClient 的简单 metrics（requests/retries/failures）"""
    try:
        metrics = client.get_metrics()
    except Exception:
        metrics = {}
    print("请求统计:", metrics)

def load_or_fetch(client: ApiClient, requester: Requester | None = None, force_fetch: bool = False, max_random_page: int = 10) -> dict:
    """
    按 era_ranges 随机构造查询 params，从 per-query 缓存读取（load_json_for_query），
    如果缓存不可用或 force_fetch 为 True 则调用 client.discover_movies 请求并保存到 per-query 缓存。
    返回合并的 dict: {"results": [...]}（保留原结构兼容性）。

    当 requester 可用时优先通过 requester.discover_movies 获取（便于统一错误提示）。
    """
    results_acc: list = []
    try:
        for era_name, start, end in era_ranges:
            year = random.randint(start, end)
            page = random.randint(1, max_random_page)
            params = {
                "primary_release_year": year,
                "page": page,
                "sort_by": "popularity.desc",
                "vote_count.gte": 1
            }
            logging.info("📡 查询 %s 年份 %d（页 %d） 参数: %s", era_name, year, page, params)

            # 首先尝试从 per-query 缓存读取
            cached = None
            try:
                if not force_fetch and hasattr(storage, "load_json_for_query"):
                    cached = storage.load_json_for_query(params, ttl_seconds=CACHE_TTL_SECONDS)
            except Exception as e:
                logging.warning("读取 per-query 缓存出错: %s", e)
                cached = None

            if cached and isinstance(cached, dict) and cached.get("results"):
                cnt = len(cached.get("results") or [])
                logging.info("🗂️ 使用缓存结果：%s (count=%d)", era_name, cnt)
                results_acc.extend(cached.get("results") or [])
                continue

            # 缓存不可用或强制刷新，发起请求（优先使用 requester 以获得友好提示）
            resp = None
            try:
                if requester:
                    logging.debug("使用 Requester 发起 discover 请求 params=%s", params)
                    resp = requester.discover_movies(params)
                else:
                    logging.debug("使用 ApiClient 直接发起 discover 请求 params=%s", params)
                    resp = client.discover_movies(params)
            except Exception as e:
                logging.warning("⚠️ TMDb 请求 %s 年代失败：%s", era_name, e)
                resp = None

            # 检查响应
            if not isinstance(resp, dict) or not resp.get("success") or not resp.get("results"):
                logging.warning("⚠️ %s 年代无有效结果或请求失败（resp=%s）", era_name, type(resp))
                # 在发生错误时展示 metrics 以便排查（不会终止流程）
                try:
                    show_metrics(client)
                except Exception:
                    pass
                continue

            # 记录响应结果数量
            try:
                rcount = len(resp.get("results") or [])
            except Exception:
                rcount = 0
            logging.info("✅ 请求成功：%s 返回 %d 条", era_name, rcount)

            # 保存到 per-query 缓存（若支持）
            try:
                if hasattr(storage, "save_json_for_query"):
                    storage.save_json_for_query(params, resp)
            except Exception:
                logging.exception("⚠️ 保存 per-query 缓存失败")

            results_acc.extend(resp.get("results") or [])

        # 最终去重并返回（保持原有逻辑）
        logging.debug("合并前总条目数：%d", len(results_acc))
        seen = set()
        deduped = []
        for mv in results_acc:
            try:
                mid = mv.get("id")
                if mid is None:
                    key = (mv.get("title") or "") + "|" + str(mv.get("release_date") or "")
                    if key in seen:
                        continue
                    seen.add(key)
                else:
                    if mid in seen:
                        continue
                    seen.add(mid)
                deduped.append(mv)
            except Exception:
                continue

        logging.info("返回去重后总条目数：%d", len(deduped))
        return {"results": deduped}
    except Exception as e:
        logging.exception("load_or_fetch 中发生错误: %s", e)
        return {"results": []}

def recommend_batch(movies: list, n: int = 3, preferences: dict = None, seed: int = None, diversify_by: str = None, exclude_ids: set = None) -> list:
    """
    批量推荐电影，支持多样性和排除已推荐的电影ID
    
    参数:
        movies: 电影列表（字典对象）
        n: 返回的推荐数量
        preferences: 包含权重、temperature等的偏好字典
        seed: 随机种子（用于可复现性）
        diversify_by: 多样性类型，可以是 "genre"、"year" 等
        exclude_ids: 要排除的电影ID集合（防止重复推荐）
    
    返回:
        推荐电影列表，按推荐程度降序
    """
    import random
    import math
    
    if not movies or not isinstance(movies, list) or n < 1:
        return []
    
    if seed is not None:
        random.seed(seed)
    
    # 如果传入了排除ID列表，过滤掉这些电影
    filtered_movies = []
    if exclude_ids:
        for movie in movies:
            movie_id = movie.get("id")
            if movie_id is not None and movie_id not in exclude_ids:
                filtered_movies.append(movie)
        
        # 如果过滤后电影数量太少（小于请求数量），回退到原始列表
        if len(filtered_movies) < n:
            filtered_movies = movies
    else:
        filtered_movies = movies
    
    # 应用权重并计算推荐分数
    prefs = preferences or {}
    weights = prefs.get("weights", {"popularity": 0.4, "rating": 0.4, "freshness": 0.2})
    temperature = prefs.get("temperature", 2.0)
    temp_balance = prefs.get("temporal_balance", False)
    temp_strength = prefs.get("temporal_balance_strength", 1.0)
    
    scored_movies = []
    for movie in filtered_movies:
        # 基本分数计算（流行度、评分、新鲜度）
        pop_score = min(1.0, (movie.get("popularity") or 0) / 1000)
        vote_avg = movie.get("vote_average", 0)
        rating_score = vote_avg / 10 if vote_avg else 0.5
        
        # 新鲜度评分（基于上映日期）
        release_date = movie.get("release_date", "")
        freshness = 0.5  # 默认中等新鲜度
        if release_date:
            try:
                year = int(release_date.split("-")[0])
                current_year = 2025  # 假设当前年份
                years_diff = current_year - year
                # 越新鲜分数越高，但超过100年的都算作经典
                if years_diff <= 0:
                    freshness = 1.0
                elif years_diff < 3:
                    freshness = 0.9
                elif years_diff < 10:
                    freshness = 0.8
                elif years_diff < 20:
                    freshness = 0.6
                elif years_diff < 50:
                    freshness = 0.4
                else:
                    freshness = 0.3
            except Exception:
                pass
                
        # 计算加权总分
        w_pop = weights.get("popularity", 0.4)
        w_rating = weights.get("rating", 0.4)
        w_freshness = weights.get("freshness", 0.2)
        
        base_score = (
            w_pop * pop_score + 
            w_rating * rating_score + 
            w_freshness * freshness
        )
        
        # 添加随机因素（温度）
        if temperature > 0:
            noise = random.random() * temperature
            score = base_score + noise
        else:
            score = base_score
            
        scored_movies.append((movie, score))
    
    # 按分数排序
    scored_movies.sort(key=lambda x: x[1], reverse=True)
    top_movies = [m for m, _ in scored_movies[:n*2]]  # 选择更多备选
    
    # 应用多样性（如果指定）
    result = []
    if diversify_by and diversify_by == "genre" and len(top_movies) > n:
        # 选择多样化的电影（按类型）
        selected_genres = set()
        for movie in top_movies:
            # 获取电影类型
            genres = []
            if "genre_ids" in movie:
                genres = movie["genre_ids"]
            elif "genres" in movie and isinstance(movie["genres"], list):
                genres = [g.get("id") for g in movie["genres"] if isinstance(g, dict)]
            
            # 检查是否与已选类型重叠
            overlap = False
            for genre in genres:
                if genre in selected_genres:
                    overlap = True
                    break
            
            # 如果没有重叠或已经选够了，添加到结果
            if not overlap or len(result) >= n-1:
                result.append(movie)
                # 记录此电影的类型
                for genre in genres:
                    if genre:
                        selected_genres.add(genre)
            
            if len(result) >= n:
                break
    else:
        # 简单返回前 N 个
        result = top_movies[:n]
    
    return result

# 添加编辑偏好的交互函数
def edit_preferences():
    """交互式编辑偏好设置"""
    prefs = load_preferences()
    
    print("\n📊 推荐偏好设置")
    print("=" * 40)
    
    print("\n1. 权重设置")
    print("  - popularity (流行度): %.2f" % prefs["weights"].get("popularity", 0.4))
    print("  - rating (评分): %.2f" % prefs["weights"].get("rating", 0.4))
    print("  - freshness (新鲜度): %.2f" % prefs["weights"].get("freshness", 0.2))
    
    print("\n2. 温度 (temperature): %.1f" % prefs.get("temperature", 2.0))
    print("   [温度越高，推荐越随机; 温度为0表示固定排序]")
    
    print("\n3. 时间平衡: %s" % ("开启" if prefs.get("temporal_balance", True) else "关闭"))
    print("   [时间平衡确保不同年代的电影都有机会被推荐]")
    
    print("\n4. 时间平衡强度: %.1f" % prefs.get("temporal_balance_strength", 1.0))
    print("   [值越大，年代分布越均匀]")
    
    print("\n5. 批量推荐多样性: %s" % (prefs.get("diversify_by", "genre") or "无"))
    print("   [确保批量推荐结果在指定维度上多样化]")
    
    print("\n6. 每类型最大条目数: %d" % prefs.get("max_items_per_genre", 2))
    print("   [批量推荐时每个类型最多出现的次数]")
    
    print("\n7. 重置为默认值")
    print("8. 保存并返回")
    print("9. 放弃修改并返回")
    
    while True:
        try:
            choice = input("\n选择要修改的选项 (1-9) > ").strip()
            
            if choice == "9":
                print("放弃修改。")
                return
                
            if choice == "8":
                # 验证并保存
                validated = validate_preferences(prefs)
                if save_preferences(validated):
                    print("✅ 偏好已保存。")
                else:
                    print("❌ 保存失败，请检查文件权限。")
                return
                
            if choice == "7":
                # 重置为默认
                confirm = input("确定要重置所有偏好为默认值吗？(y/n) > ").strip().lower()
                if confirm == "y":
                    prefs = DEFAULT_PREFERENCES.copy()
                    print("✅ 已重置为默认值。")
                continue
                
            if choice == "1":
                # 编辑权重
                try:
                    p_weight = float(input("流行度权重 (0-1) > ").strip() or prefs["weights"].get("popularity", 0.4))
                    r_weight = float(input("评分权重 (0-1) > ").strip() or prefs["weights"].get("rating", 0.4))
                    f_weight = float(input("新鲜度权重 (0-1) > ").strip() or prefs["weights"].get("freshness", 0.2))
                    
                    # 规范化权重
                    total = p_weight + r_weight + f_weight
                    if total > 0:
                        prefs["weights"]["popularity"] = p_weight / total
                        prefs["weights"]["rating"] = r_weight / total
                        prefs["weights"]["freshness"] = f_weight / total
                        print(f"✅ 权重已更新并归一化：流行度={prefs['weights']['popularity']:.2f}, " +
                              f"评分={prefs['weights']['rating']:.2f}, 新鲜度={prefs['weights']['freshness']:.2f}")
                    else:
                        print("❌ 权重总和必须大于0。")
                except ValueError:
                    print("❌ 请输入有效数字。")
                    
            elif choice == "2":
                # 编辑温度
                try:
                    temp = float(input("温度 (0-10，推荐2-5) > ").strip() or prefs.get("temperature", 2.0))
                    prefs["temperature"] = max(0, min(10, temp))
                    print(f"✅ 温度已设置为：{prefs['temperature']}")
                except ValueError:
                    print("❌ 请输入有效数字。")
                    
            elif choice == "3":
                # 编辑时间平衡开关
                tb = input("时间平衡 (y/n) > ").strip().lower()
                if tb in ("y", "yes", "1", "true"):
                    prefs["temporal_balance"] = True
                    print("✅ 时间平衡已开启。")
                elif tb in ("n", "no", "0", "false"):
                    prefs["temporal_balance"] = False
                    print("✅ 时间平衡已关闭。")
                else:
                    print("❌ 未更改时间平衡设置。")
                    
            elif choice == "4":
                # 编辑时间平衡强度
                try:
                    tbs = float(input("时间平衡强度 (0-5) > ").strip() or prefs.get("temporal_balance_strength", 1.0))
                    prefs["temporal_balance_strength"] = max(0, min(5, tbs))
                    print(f"✅ 时间平衡强度已设置为：{prefs['temporal_balance_strength']}")
                except ValueError:
                    print("❌ 请输入有效数字。")
                    
            elif choice == "5":
                # 编辑多样性
                print("多样性选项：")
                print("1. 无")
                print("2. 类型 (genre)")
                print("3. 年代 (year)")
                div = input("选择多样性方式 (1-3) > ").strip()
                
                if div == "1":
                    prefs["diversify_by"] = None
                    print("✅ 批量推荐将不进行多样性处理。")
                elif div == "2":
                    prefs["diversify_by"] = "genre"
                    print("✅ 批量推荐将按类型多样化。")
                elif div == "3":
                    prefs["diversify_by"] = "year"
                    print("✅ 批量推荐将按年代多样化。")
                else:
                    print("❌ 未更改多样性设置。")
                    
            elif choice == "6":
                # 编辑每类型最大条目数
                try:
                    max_items = int(input("每类型最大条目数 (1-10) > ").strip() or prefs.get("max_items_per_genre", 2))
                    prefs["max_items_per_genre"] = max(1, min(10, max_items))
                    print(f"✅ 每类型最大条目数已设置为：{prefs['max_items_per_genre']}")
                except ValueError:
                    print("❌ 请输入有效整数。")
                    
            else:
                print("❌ 无效选项，请输入1-9。")
                
        except Exception as e:
            print(f"❌ 处理输入时出错: {e}")

def interactive_loop(client: ApiClient, requester: Requester):
    print("✨ 随机电影推荐器 ✨")
    print("按回车随机推荐一部；输入 b 列出 3 个推荐；输入 r 回源刷新；输入 q 退出。\n")

    # 添加一个集合记录最近推荐过的电影ID，防止短时间内重复推荐
    recently_recommended_ids = set()

    # 获取 TMDb 类型映射（优先中文/英文）
    try:
        zh_map = get_genre_map(client, language="zh-CN") or {}
    except Exception:
        zh_map = {}
    try:
        en_map = get_genre_map(client, language="en-US") or {}
    except Exception:
        en_map = {}

    # 合并映射：键为小写名称 -> id；id_to_name 优先中文名
    genre_map = {}
    id_to_name: dict = {}
    for name, gid in (en_map or {}).items():
        if name and gid:
            genre_map[name.strip().lower()] = gid
            if gid not in id_to_name:
                id_to_name[gid] = name
    for name, gid in (zh_map or {}).items():
        if name and gid:
            genre_map[name.strip().lower()] = gid
            id_to_name[gid] = name  # 覆盖为中文显示

    # 构建 display_map（按 id 去重并挑首选显示名）
    display_map: dict = {}
    seen_gids = set()
    for gid, pname in id_to_name.items():
        if not pname:
            continue
        key = pname.strip()
        if not key:
            continue
        display_map[key.strip().lower()] = gid
        seen_gids.add(gid)
    for name, gid in (genre_map or {}).items():
        if gid in seen_gids:
            continue
        if not name:
            continue
        display_map[name.strip().lower()] = gid
        seen_gids.add(gid)

    # 加入常见中文别名映射到已知英文名的 id（方便用户输入中文别名）
    for cn, en in GENRE_ALIASES.items():
        ek = en.strip().lower()
        if ek in genre_map:
            display_map[cn.strip().lower()] = genre_map[ek]

    # display_items: list of (gid, display_lower_name) sorted by display label
    display_items = sorted(
        ((v, k) for k, v in display_map.items()),
        key=lambda vi: (id_to_name.get(vi[0]) or vi[1]).lower()
    )

    # 为交互构建 name->id 映射（使用首选显示名）
    display_name_map = {}
    for gid, lower_name in display_items:
        label = id_to_name.get(gid) or lower_name
        display_name_map[str(label).strip().lower()] = gid

    current_genre_name = ""
    current_genre_id = None

    # 优先让用户从去重后的 display_map 选择
    if display_items:
        print("可用类型已从 TMDb 拉取，可直接选择：")
        sel_name, sel_id = _choose_genre_from_map(display_name_map)
        if sel_id:
            current_genre_name = sel_name
            current_genre_id = sel_id
            print(f"🔎 已设置类型过滤：{sel_name}")
        else:
            init_genre = input("或直接输入想看的电影类型（可留空）> ").strip()
            if init_genre:
                ig = init_genre.lower()
                if ig in display_name_map:
                    current_genre_id = display_name_map[ig]
                    current_genre_name = ig
                    print(f"🔎 已设置类型过滤：{init_genre}")
                elif ig in genre_map:
                    current_genre_id = genre_map[ig]
                    current_genre_name = ig
                    print(f"🔎 已设置类型过滤：{init_genre}")
                else:
                    mapped = GENRE_ALIASES.get(init_genre) or GENRE_ALIASES.get(init_genre.strip())
                    if mapped and mapped.strip().lower() in genre_map:
                        current_genre_id = genre_map[mapped.strip().lower()]
                        current_genre_name = mapped.strip().lower()
                        print(f"🔎 已通过别名映射设置类型过滤：{init_genre} -> {mapped}")
                    else:
                        current_genre_name = init_genre
                        print(f"🔎 将尝试基于条目模糊匹配类型：{init_genre}")
    else:
        init_genre = input("输入想看的电影类型（可留空，例如: Drama / 剧情）> ").strip()
        if init_genre:
            ig = init_genre.lower()
            if ig in genre_map:
                current_genre_id = genre_map[ig]
                current_genre_name = ig
                print(f"🔎 已设置类型过滤：{init_genre}")
            else:
                current_genre_name = init_genre
                print(f"🔎 将尝试基于条目模糊匹配类型：{init_genre}")

    # 载入数据（优先 per-query 缓存），传入 requester 以便统一错误处理
    data = load_or_fetch(client, requester=requester, force_fetch=False)
    if not data:
        print("🚫 无数据可用（既无法从 API 获取也无缓存）。")
        return

    results = data.get("results") or []
    if not results:
        print("🔍 没有可推荐的影片。")
        return

    last_chosen = None

    def _apply_genre_filter(rs: list) -> list:
        if not rs:
            return []
        if not current_genre_id and not current_genre_name:
            return rs
        return filter_by_genre(rs, genre_name=current_genre_name, genre_id=current_genre_id) or []

    try:
        while True:
            cmd = input("按回车获取推荐 / b 批量 / r 刷新 / g 更改类型 / p 偏好设置 / f 收藏 / fav-list / fav-remove / q 退出 > ").strip().lower()
            if cmd == "q":
                print("👋 再见！")
                return

            if cmd == "g":
                if display_name_map:
                    print("输入 s 从 TMDb 类型列表选择，或直接输入类型名（回车取消）。")
                    sub = input("选择 s 或直接输入> ").strip()
                    if sub.lower() == "s":
                        # 重新用 display_name_map 选择
                        new_name, new_id = _choose_genre_from_map(display_name_map)
                        if new_id:
                            current_genre_name = new_name
                            current_genre_id = new_id
                            print(f"🔎 已设置类型过滤：{new_name}")
                        else:
                            print("未选择任何类型。")
                        continue
                    newg = sub
                else:
                    newg = input("输入要过滤的类型名（留空取消类型过滤）> ").strip()

                if not newg:
                    current_genre_name = ""
                    current_genre_id = None
                    print("🔎 已取消类型过滤。")
                else:
                    ng = newg.lower()
                    if display_name_map and ng in display_name_map:
                        current_genre_id = display_name_map[ng]
                        current_genre_name = ng
                        print(f"🔎 已设置类型过滤：{newg}")
                    elif ng in genre_map:
                        current_genre_id = genre_map[ng]
                        current_genre_name = ng
                        print(f"🔎 已设置类型过滤：{newg}")
                    else:
                        mapped = GENRE_ALIASES.get(newg) or GENRE_ALIASES.get(newg.strip())
                        if mapped and mapped.strip().lower() in genre_map:
                            current_genre_id = genre_map[mapped.strip().lower()]
                            current_genre_name = mapped.strip().lower()
                            print(f"🔎 已通过别名映射设置类型过滤：{newg} -> {mapped}")
                        else:
                            current_genre_name = newg
                            current_genre_id = None
                            print(f"🔎 将尝试基于条目模糊匹配类型：{newg}")
                continue

            if cmd == "fav-list":
                favs = storage.list_favorites()
                if not favs:
                    print("（无收藏）")
                else:
                    print("\n📚 收藏列表：\n")
                    for f in favs:
                        print(format_movie(f))
                        print("-" * 40)
                continue

            if cmd == "fav-remove":
                to_id = input("输入要删除的电影 id > ").strip()
                ok, mid, err = ensure_positive_int(to_id, "movie id")
                if not ok:
                    print(f"无效 id：{err}")
                else:
                    removed = storage.remove_favorite(mid)
                    print("已删除。" if removed else "未找到指定 id 的收藏。")
                continue

            if cmd == "r":
                # 刷新时清空已推荐列表，允许重新推荐之前的电影
                recently_recommended_ids.clear()
                
                data = load_or_fetch(client, requester=requester, force_fetch=True)
                if not data:
                    print("⚠️ 刷新失败，仍使用旧缓存（若有）。")
                    try:
                        data = storage.load_json(CACHE_FILE)
                    except Exception:
                        data = None
                results = (data.get("results") or []) if data else []
                if not results:
                    print("🔍 无可用结果。")
                    continue

            if not results:
                print("🔍 当前无可用影片。")
                continue

            filtered_results = _apply_genre_filter(results)
            if current_genre_name and not filtered_results:
                print(f"⚠️ 未找到匹配类型 '{current_genre_name}' 的影片，会在全部结果中随机推荐。")
                filtered_results = results

            if cmd == "b":
                prefs = {
                    "weights": {"popularity": 0.3, "rating": 0.3, "freshness": 0.4},
                    "temperature": 3.0,
                    "temporal_balance": True,
                    "temporal_balance_strength": 1.5
                }
                
                # 使用随机种子增加多样性
                random_seed = random.randint(1, 10000)
                
                # 传入排除ID列表，防止短期内重复推荐
                batch = recommend_batch(
                    filtered_results, 
                    n=3, 
                    preferences=prefs, 
                    seed=random_seed, 
                    diversify_by="genre",
                    exclude_ids=recently_recommended_ids
                )
                
                # 记录本次推荐的电影ID
                for mv in batch:
                    if "id" in mv and mv["id"]:
                        recently_recommended_ids.add(mv["id"])
                
                # 限制记忆集合大小，避免无限增长
                if len(recently_recommended_ids) > 50:
                    # 保留最近的30个ID
                    recently_recommended_ids = set(list(recently_recommended_ids)[-30:])
                
                print("\n🎯 批量推荐：\n")
                for i, mv in enumerate(batch, 1):
                    mv_disp = dict(mv)
                    gids = mv.get("genre_ids") or []
                    if isinstance(gids, (list, tuple)) and id_to_name:
                        mv_disp["genre_names"] = [id_to_name.get(g) for g in gids if id_to_name.get(g)]
                    elif mv.get("genres"):
                        mv_disp["genre_names"] = [g.get("name") for g in mv.get("genres") if isinstance(g, dict) and g.get("name")]
                    era = mv_disp.get("_era", "")
                    print(f"{i}. [{era}]")
                    print(format_movie(mv_disp))
                    print("-" * 40)
                print()
                last_chosen = batch[-1] if batch else None
                continue

            prefs = {
                "weights": {"popularity": 0.3, "rating": 0.3, "freshness": 0.4},
                "temperature": 3.0,
                "temporal_balance": True,
                "temporal_balance_strength": 1.5
            }
            
            # 单个推荐也排除已推荐过的电影
            filtered_for_single = [m for m in filtered_results if m.get("id") not in recently_recommended_ids]
            if len(filtered_for_single) < 10:  # 如果过滤后太少，使用原始列表
                filtered_for_single = filtered_results
            
            chosen = pick_random_movie(filtered_for_single, preferences=prefs, seed=random.randint(1, 10000))
            if not chosen:
                chosen = random.choice(filtered_results if filtered_results else results)
            
            # 记录推荐ID
            if "id" in chosen and chosen["id"]:
                recently_recommended_ids.add(chosen["id"])
            
            # 限制记忆集合大小
            if len(recently_recommended_ids) > 50:
                recently_recommended_ids = set(list(recently_recommended_ids)[-30:])
            
            chosen_disp = dict(chosen)
            gids = chosen.get("genre_ids") or []
            if isinstance(gids, (list, tuple)) and id_to_name:
                chosen_disp["genre_names"] = [id_to_name.get(g) for g in gids if id_to_name.get(g)]
            elif chosen.get("genres"):
                chosen_disp["genre_names"] = [g.get("name") for g in chosen.get("genres") if isinstance(g, dict) and g.get("name")]
            print("\n" + format_movie(chosen_disp) + "\n")
            last_chosen = chosen

            if cmd == "f":
                if last_chosen:
                    ok = storage.save_favorite(last_chosen)
                    if ok:
                        mid = last_chosen.get("id")
                        print(f"✅ 已收藏。id={mid}" if mid is not None else "✅ 已收藏。")
                    else:
                        print("⚠️ 收藏失败。")
                else:
                    print("⚠️ 尚未展示任何影片，无法收藏。")
                    
            # 处理偏好设置命令
            if cmd == "p":
                edit_preferences()
                continue
    except KeyboardInterrupt:
        print("\n👋 已取消。")

def main():
    # 确保默认偏好文件存在
    create_default_preferences_if_missing()
    api_key = os.getenv("TMDB_API_KEY") or get_tmdb_key()
    if not api_key:
        print("❗ 未配置 TMDB_API_KEY。请设置环境变量或在 config 中提供。")
        return
    client = ApiClient(base_url=os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3"),
                      api_key=api_key,
                      key_type=os.getenv("TMDB_KEY_TYPE", "v3"),
                      timeout=int(os.getenv("REQUEST_TIMEOUT", 30)),
                      max_retries=int(os.getenv("MAX_RETRIES", 2)))
    # 使用 Requester 包装 client，以便在交互中获得友好提示与一致的错误处理
    requester = Requester(client)
    interactive_loop(client, requester)

if __name__ == "__main__":
    main()