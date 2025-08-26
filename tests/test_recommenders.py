from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src import recommenders as rec

def make_movie(mid, title=None, popularity=0.0, vote_average=None, release_date="", genre_ids=None, adult=False, vote_count=0):
    return {
        "id": mid,
        "title": title or f"Movie {mid}",
        "popularity": popularity,
        "vote_average": vote_average,
        "vote_count": vote_count,
        "release_date": release_date,
        "genre_ids": genre_ids or [],
        "adult": adult,
    }

def test_sanitize_filters_invalid_and_dedups():
    raw = [None, {"id": "x"}, {"id": 1, "title": "A"}, {"id": 1, "title": "A dup"}, {"id":2, "name":"B"}]
    out = rec.sanitize_movies(raw)
    ids = [m["id"] for m in out]
    assert ids == [1, 2]
    assert out[0]["title"] == "A"
    assert out[1]["title"] == "B"

def test_score_movies_respects_preferences_and_filters():
    m1 = make_movie(1, popularity=20.0, vote_average=7.0, release_date="2024-01-01", genre_ids=[101], adult=False, vote_count=50)
    m2 = make_movie(2, popularity=5.0, vote_average=3.0, release_date="2010-01-01", genre_ids=[], adult=False, vote_count=5)
    m3 = make_movie(3, popularity=50.0, vote_average=9.0, release_date="2020-01-01", genre_ids=[999], adult=True, vote_count=100)
    prefs = {"preferred_genres":[101], "exclude_genres": [], "exclude_adult": True, "min_vote_count": 10}
    scored = rec.score_movies([m1,m2,m3], preferences=prefs)
    # adult movie should be filtered out; m1 should rank above m2
    ids = [m["id"] for m, s in scored]
    assert 3 not in ids
    assert ids[0] == 1

def test_pick_random_movie_deterministic_with_seed():
    movies = [make_movie(i, popularity=float(i)) for i in range(1,6)]
    a = rec.pick_random_movie(movies, seed=123)
    b = rec.pick_random_movie(movies, seed=123)
    assert a["id"] == b["id"]

def test_recommend_batch_diversity_and_count():
    movies = [make_movie(i, popularity=10-i, genre_ids=[i]) for i in range(1,10)]
    batch = rec.recommend_batch(movies, n=3, seed=42, diversify_by="genre")
    assert len(batch) == 3
    ids = [m["id"] for m in batch]
    assert len(set(ids)) == 3
    # 不同电影应有不同 genre tuples (since we used unique single-genre ids)
    genres = [tuple(sorted(m.get("genre_ids") or [])) for m in batch]
    assert len(set(genres)) == 3

def test_pick_random_movie_fallback_topk_when_zero_scores():
    movies = [make_movie(i, popularity=0.0, vote_average=None) for i in range(1,8)]
    chosen = rec.pick_random_movie(movies, seed=7)
    assert chosen is not None
    assert chosen["id"] in [m["id"] for m in movies]