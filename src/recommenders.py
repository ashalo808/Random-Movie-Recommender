import math
import random
import logging
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def sanitize_movies(movies: list) -> list:
    # ...existing code...
    if not movies:
        return []

    if isinstance(movies, dict) and "results" in movies:
        movies = movies.get("results") or []

    if not isinstance(movies, list):
        logger.warning("sanitize_movies: 传入非列表类型，尝试转换失败")
        return []

    seen_ids = set()
    out: List[Dict[str, Any]] = []

    for item in movies:
        if not item or not isinstance(item, dict):
            continue
        mid = item.get("id")
        try:
            mid = int(mid)
        except Exception:
            continue
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        title = item.get("title") or item.get("name") or item.get("original_title") or ""
        if not isinstance(title, str):
            title = str(title) if title is not None else ""
        title = title.strip()
        if not title:
            title = f"Untitled ({mid})"
        overview = item.get("overview") or ""
        overview = overview if isinstance(overview, str) else str(overview)
        release_date = item.get("release_date") or item.get("first_air_date") or ""
        release_date = release_date if isinstance(release_date, str) else str(release_date)
        try:
            vote_average = float(item.get("vote_average")) if item.get("vote_average") is not None else None
        except Exception:
            vote_average = None
        try:
            vote_count = int(item.get("vote_count")) if item.get("vote_count") is not None else 0
        except Exception:
            vote_count = 0
        try:
            popularity = float(item.get("popularity")) if item.get("popularity") is not None else 0.0
        except Exception:
            popularity = 0.0
        poster_path = item.get("poster_path")
        backdrop_path = item.get("backdrop_path")
        adult = bool(item.get("adult")) if "adult" in item else False
        genre_ids = item.get("genre_ids") or item.get("genres") or []
        if isinstance(genre_ids, list) and genre_ids and isinstance(genre_ids[0], dict):
            try:
                genre_ids = [int(g.get("id")) for g in genre_ids if g.get("id") is not None]
            except Exception:
                genre_ids = []
        sanitized = {
            "id": mid,
            "title": title,
            "original_title": item.get("original_title") or "",
            "overview": overview,
            "release_date": release_date,
            "vote_average": vote_average,
            "vote_count": vote_count,
            "popularity": popularity,
            "poster_path": poster_path,
            "backdrop_path": backdrop_path,
            "adult": adult,
            "genre_ids": genre_ids,
            "raw": item,
        }
        out.append(sanitized)
    return out

def _normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mx <= mn:
        return [1.0 for _ in values]
    return [(v - mn) / (mx - mn) for v in values]

def _recency_score(release_date: str, max_years: int = 10) -> float:
    """
    返回 0..1 的新鲜度分数，越新的分数越高。max_years 控制衰减尺度。
    """
    if not release_date:
        return 0.0
    try:
        year = int(release_date.split("-")[0])
    except Exception:
        return 0.0
    cur = datetime.now(timezone.utc).year
    age = max(0, cur - year)
    # 指数衰减，避免线性过度偏好最新年份；max_years 控制衰减速度
    tau = max(1.0, max_years / 2.0)
    score = math.exp(-age / tau)
    return float(score)

def score_movies(movies: list, preferences: Optional[Dict[str, Any]] = None) -> List[Tuple[Dict[str, Any], float]]:
    """
    为 movies 列表计算综合评分，返回 (movie, score) 列表。
    preferences 支持键：
      - preferred_genres: List[int]
      - exclude_genres: List[int]
      - exclude_adult: bool
      - min_vote_count: int
      - weights: dict with keys popularity, rating, freshness, genre_boost
      - recency_years: int
    """
    prefs = preferences or {}
    preferred_genres = set(prefs.get("preferred_genres") or [])
    exclude_genres = set(prefs.get("exclude_genres") or [])
    exclude_adult = bool(prefs.get("exclude_adult")) if "exclude_adult" in prefs else True
    min_vote_count = int(prefs.get("min_vote_count", 0))
    weights = prefs.get("weights", {})
    w_pop = float(weights.get("popularity", 0.5))
    w_rating = float(weights.get("rating", 0.3))
    w_fresh = float(weights.get("freshness", 0.2))
    genre_boost = float(weights.get("genre_boost", 0.3))
    recency_years = int(prefs.get("recency_years", 10))

    sanitized = sanitize_movies(movies)
    if not sanitized:
        return []

    # 过滤规则（先过滤掉明显不满足的）
    candidates = []
    for m in sanitized:
        if exclude_adult and m.get("adult"):
            continue
        if min_vote_count and (m.get("vote_count", 0) < min_vote_count):
            continue
        if exclude_genres:
            gids = set(m.get("genre_ids") or [])
            if gids & exclude_genres:
                continue
        candidates.append(m)
    if not candidates:
        return []

    pops = [float(m.get("popularity") or 0.0) for m in candidates]
    ratings = [float(m.get("vote_average") or 0.0) for m in candidates]
    recencies = [_recency_score(m.get("release_date", ""), max_years=recency_years) for m in candidates]

    npop = _normalize(pops)
    nrat = _normalize(ratings)
    nrec = _normalize(recencies)

    scored = []
    for m, spop, srat, srec in zip(candidates, npop, nrat, nrec):
        base_score = w_pop * spop + w_rating * srat + w_fresh * srec
        # 类型偏好加分
        if preferred_genres:
            gids = set(m.get("genre_ids") or [])
            overlap = len(gids & preferred_genres)
            if overlap:
                base_score += genre_boost * (overlap / max(1, len(preferred_genres)))
        scored.append((m, float(base_score)))
        
    if prefs.get("temporal_balance"):
        strength = float(prefs.get("temporal_balance_strength", 0.7))  # 0..1, 越大平衡越强
        # 统计年份分布
        year_counts = {}
        for m, s in scored:
            y = (m.get("release_date") or "")[:4]
            year_counts[y] = year_counts.get(y, 0) + 1
        if year_counts:
            max_count = max(year_counts.values())
            balanced = []
            for m, s in scored:
                y = (m.get("release_date") or "")[:4]
                cnt = year_counts.get(y, 1)
                # 惩罚因子，年份样本越多惩罚越大
                penalty = 1.0 / (1.0 + strength * ((cnt - 1) / max(1, max_count)))
                balanced.append((m, s * penalty))
            scored = balanced
    
    # 若所有 score 为 0，提升 popularity 排序作为保底
    return sorted(scored, key=lambda t: t[1], reverse=True)

def pick_random_movie(movies: list, preferences: Optional[Dict[str, Any]] = None, seed: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    支持 preferences 中添加:
      - temperature: float (>0)，越大越随机（更均匀），越小越挑高分
      - temporal_balance: bool
      - temporal_balance_strength: float
    """
    prefs = preferences or {}
    temperature = float(prefs.get("temperature", 1.0))
    scored = score_movies(movies, preferences=prefs)
    if not scored:
        return None
    movies_list, scores = zip(*scored)
    total = sum(scores)
    rnd = random.Random(seed)
    if total > 0:
        try:
            # softmax-ish: convert scores -> weights with temperature
            if temperature <= 0:
                temperature = 1.0
            # 为数值稳定性处理：减去最大值
            mx = max(scores)
            exp_weights = [math.exp((s - mx) / float(temperature)) for s in scores]
            weights = [w / sum(exp_weights) for w in exp_weights]
            idx = rnd.choices(range(len(movies_list)), weights=weights, k=1)[0]
            return movies_list[idx]
        except Exception as e:
            logger.exception("按分数/温度选择失败，回退到 top1: %s", e)
    topk = movies_list[:min(10, len(movies_list))]
    return rnd.choice(list(topk))

def recommend_batch(movies: list, n: int = 5, preferences: Optional[Dict[str, Any]] = None, seed: Optional[int] = None, diversify_by: Optional[str] = "genre") -> List[Dict[str, Any]]:
    """
    返回 n 个不重复的推荐。策略：
      - 先根据 score 排序
      - 按概率或贪心抽取，尝试多样化（不同 genre）
    diversify_by: "genre" 或 None
    """
    if n <= 0:
        return []
    scored = score_movies(movies, preferences)
    if not scored:
        return []
    items = [m for m, s in scored]
    rnd = random.Random(seed)
    if n >= len(items):
        return items.copy()

    chosen = []
    used_genres = set()
    attempts = 0
    idx_pool = list(range(len(items)))
    while len(chosen) < n and attempts < len(items) * 2:
        attempts += 1
        # 按指数衰减概率（更高分更可能）
        weights = [max(0.001, s) for _, s in scored]
        try:
            i = rnd.choices(idx_pool, weights=[weights[j] for j in idx_pool], k=1)[0]
        except Exception:
            i = rnd.choice(idx_pool)
        candidate = items[i]
        if diversify_by == "genre":
            gids = tuple(sorted(set(candidate.get("genre_ids") or [])))
            if gids and gids in used_genres:
                # 有相同主 genre 的尽量避免，尝试跳过
                idx_pool.remove(i)
                continue
            used_genres.add(gids)
        chosen.append(candidate)
        if i in idx_pool:
            idx_pool.remove(i)
    # 如果不够，补齐前 n 个
    if len(chosen) < n:
        for it in items:
            if it not in chosen:
                chosen.append(it)
            if len(chosen) >= n:
                break
    return chosen[:n]

# 保留向后兼容的接口名
def pick_random_movie_simple(movies: list) -> dict | None:
    return pick_random_movie(movies)