import pytest
from typing import Any

# python

from src.utils import (
    format_movie,
    ensure_positive_int,
    get_genre_map,
    filter_by_genre,
    validate_api_key,
)


def test_format_movie_basic_and_truncate():
    long_overview = "A" * 300
    movie = {
        "title": "My Movie",
        "release_date": "2020-05-01",
        "vote_average": 7.8,
        "overview": long_overview,
        "genre_names": ["Action", "Drama"],
    }
    out = format_movie(movie)
    assert "My Movie" in out
    assert "(2020)" in out
    assert "评分: 7.8" in out
    assert "类型: Action, Drama" in out
    # 简介应被截断且非空
    assert "（暂无简介）" not in out
    # 最后一行为简介，去除前缀 "📝 " 后长度不超过 140
    last_line = out.splitlines()[-1]
    if last_line.startswith("📝 "):
        overview_text = last_line[len("📝 ") :]
    else:
        overview_text = last_line
    assert len(overview_text) <= 140


def test_format_movie_non_dict_returns_placeholder():
    assert format_movie(None) == "<无效电影数据>"
    assert format_movie("string") == "<无效电影数据>"


def test_ensure_positive_int_valid_and_invalid():
    ok, val, err = ensure_positive_int("10", name="n")
    assert ok is True and val == 10 and err is None

    ok, val, err = ensure_positive_int(5)
    assert ok is True and val == 5 and err is None

    ok, val, err = ensure_positive_int("abc", name="count")
    assert ok is False and val is None and isinstance(err, str)

    ok, val, err = ensure_positive_int(0, name="zero")
    assert ok is False and val is None and "正整数" in err

    ok, val, err = ensure_positive_int(-3, name="neg")
    assert ok is False and val is None and "正整数" in err

    ok, val, err = ensure_positive_int(None, name="x")
    assert ok is False and val is None and "不能为空" in err


def test_validate_api_key_cases():
    assert validate_api_key("abcdef") is True
    assert validate_api_key("   abcdef   ") is True
    assert validate_api_key("short") is False  # <6 chars
    assert validate_api_key("") is False
    assert validate_api_key(None) is False
    assert validate_api_key(12345) is False


class DummyClient:
    def __init__(self, data: Any):
        self._data = data

    def get_genres(self, language="zh-CN"):
        return self._data


def test_get_genre_map_from_client_dict():
    data = {"genres": [{"id": 1, "name": "Action"}, {"id": 2, "name": "Drama"}]}
    client = DummyClient(data)
    mapping = get_genre_map(client, language="en")
    assert mapping.get("action") == 1
    assert mapping.get("drama") == 2


def test_get_genre_map_from_client_list_and_english_name():
    data = [{"id": 10, "english_name": "Sci-Fi"}, {"id": 20, "name": "Comedy"}]
    client = DummyClient(data)
    mapping = get_genre_map(client)
    assert mapping.get("sci-fi") == 10
    assert mapping.get("comedy") == 20


def test_filter_by_genre_id_priority():
    movies = [
        {"id": 1, "title": "A", "genre_ids": [5, 8]},
        {"id": 2, "title": "B", "genre_ids": [3]},
    ]
    out = filter_by_genre(movies, genre_id=5)
    assert len(out) == 1
    assert out[0]["id"] == 1
    # original not modified
    assert movies[0].get("genre_ids") == [5, 8]


def test_filter_by_genre_name_in_genres_field():
    movies = [
        {"id": 1, "genres": [{"id": 2, "name": "Drama"}], "title": "X"},
        {"id": 2, "genres": [{"id": 3, "name": "Action"}], "title": "Y"},
    ]
    out = filter_by_genre(movies, genre_name="drama")
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_filter_by_genre_text_search_fallback():
    movies = [
        {"id": 1, "title": "Romantic Tale", "overview": "A touching story"},
        {"id": 2, "title": "Sci-Fi Epic", "overview": "Space travel"},
    ]
    out = filter_by_genre(movies, genre_name="romantic")
    assert len(out) == 1
    assert out[0]["id"] == 1