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
from src.requester import send_request
from src.endpoints import POPULAR, SEARCH, make_endpoint
from src.api_client import ApiClient
from src.recommenders import pick_random_movie, recommend_batch

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
    按 era_ranges 随机构造查询 params，从 per-query 缓存读取（load_json_for_query），
    如果缓存不可用或 force_fetch 为 True 则调用 client.discover_movies 请求并保存到 per-query 缓存。
    返回合并的 dict: {"results": [...]}（保留原结构兼容性）。
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
                # 临时放宽门槛，便于调试：大多数条目 vote_count 可能 <50
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

            # 缓存不可用或强制刷新，发起请求
            try:
                logging.debug("发起 TMDb discover 请求 params=%s", params)
                resp = client.discover_movies(params)
            except Exception as e:
                logging.warning("⚠️ TMDb 请求 %s 年代失败：%s", era_name, e)
                resp = None
                # fallback: 尝试用 requester 直接发起请求
                try:
                    sess = getattr(client, "session", requests.Session())
                    raw = send_request(sess, getattr(client, "base_url", "https://api.themoviedb.org/3"), "GET", "discover/movie", params=params)
                    logging.debug("requester fallback raw keys: %s", list(raw.keys()) if isinstance(raw, dict) else type(raw))
                    if raw and raw.get("results"):
                        resp = {"success": True, "results": raw.get("results") or [], "data": raw.get("data") if isinstance(raw, dict) else raw}
                    else:
                        logging.warning("requester fallback 未返回 results: %s", raw)
                        resp = None
                except Exception as e2:
                    logging.warning("requester fallback 异常: %s", e2)
                    resp = None

            # 检查响应
            if not isinstance(resp, dict) or not resp.get("success") or not resp.get("results"):
                logging.warning("⚠️ %s 年代无有效结果或请求失败（resp=%s）", era_name, type(resp))
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

        # 最终去重并返回
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
    
def interactive_loop(client: ApiClient):
    print("✨ 随机电影推荐器 ✨")
    print("按回车随机推荐一部；输入 b 列出 3 个推荐；输入 r 回源刷新；输入 q 退出。\n")

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

    # 载入数据（优先 per-query 缓存）
    data = load_or_fetch(client, force_fetch=False)
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
            cmd = input("按回车获取推荐 / b 批量 / r 刷新 / g 更改类型 / f 收藏 / fav-list / fav-remove / q 退出 > ").strip().lower()
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
                data = load_or_fetch(client, force_fetch=True)
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
                batch = recommend_batch(filtered_results, n=3, preferences=prefs, seed=None, diversify_by="genre")
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
            chosen = pick_random_movie(filtered_results, preferences=prefs, seed=None)
            if not chosen:
                chosen = random.choice(filtered_results if filtered_results else results)
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