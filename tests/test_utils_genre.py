import pytest
from src.utils import get_genre_map, filter_by_genre

class FakeClientOk:
    def get_genres(self, language="zh-CN"):
        return {"genres": [{"id": 18, "name": "Drama"}, {"id": 35, "name": "喜剧"}]}

class FakeClientBad:
    def get_genres(self, language="zh-CN"):
        raise RuntimeError("network")

def test_get_genre_map_success():
    c = FakeClientOk()
    m = get_genre_map(c)
    assert isinstance(m, dict)
    assert m.get("drama") == 18
    # 中文名字也应使用原文作为键（lower 不改变汉字）
    assert m.get("喜剧") == 35

def test_get_genre_map_failure():
    c = FakeClientBad()
    m = get_genre_map(c)
    assert m == {}

def test_filter_by_genre_by_id():
    movies = [
        {"id": 1, "title": "A", "genre_ids": [18, 35]},
        {"id": 2, "title": "B", "genre_ids": [12]}
    ]
    out = filter_by_genre(movies, genre_id=18)
    assert len(out) == 1
    assert out[0]["id"] == 1
    # 原 movies 不应被修改
    assert "_matched_genre" not in movies[0]

def test_filter_by_genre_by_genres_name():
    movies = [
        {"id": 3, "title": "C", "genres": [{"id":18, "name":"Drama"}]},
        {"id": 4, "title": "D", "genres": [{"id":35, "name":"Comedy"}]}
    ]
    out = filter_by_genre(movies, genre_name="drama")
    assert len(out) == 1
    assert out[0]["id"] == 3

def test_filter_by_genre_by_text():
    movies = [
        {"id": 5, "title": "Romantic Comedy Special", "overview": "funny and warm"},
        {"id": 6, "title": "Serious Film", "overview": "dark themes"}
    ]
    out = filter_by_genre(movies, genre_name="comedy")
    assert len(out) == 1
    assert out[0]["id"] == 5

def test_filter_no_side_effects():
    movie = {"id": 7, "title": "X", "overview": "overview text"}
    movies = [movie]
    out = filter_by_genre(movies, genre_name="x")
    assert out and out[0]["id"] == 7
    # 确认原 movie 未被修改
    assert movie.get("_matched_genre") is None