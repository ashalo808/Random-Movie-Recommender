import os
from pathlib import Path
import pytest
from src import storage

def setup_tmp_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "cache"
    fav_file = data_dir / "favorites.json"
    monkeypatch.setattr(storage, "_CACHE_SUBDIR", cache_dir)
    monkeypatch.setattr(storage, "_FAVORITES_FILE", fav_file)
    return data_dir

def test_cache_save_and_load(tmp_path, monkeypatch):
    setup_tmp_dirs(tmp_path, monkeypatch)
    params = {"q": "testing", "page": 1}
    payload = {"success": True, "results": [{"id": 1}]}
    ok = storage.save_json_for_query(params, payload)
    assert ok is True
    loaded = storage.load_json_for_query(params)
    assert isinstance(loaded, dict)
    assert loaded.get("success") is True
    path = storage.make_cache_path_for_query(params)
    assert Path(path).exists()

def test_cache_expiry(tmp_path, monkeypatch):
    setup_tmp_dirs(tmp_path, monkeypatch)
    params = {"q": "expire", "page": 2}
    payload = {"x": 1}
    storage.save_json_for_query(params, payload)
    loaded_ok = storage.load_json_for_query(params, ttl_seconds=3600)
    assert loaded_ok is not None
    loaded_none = storage.load_json_for_query(params, ttl_seconds=0)
    assert loaded_none is None

def test_favorites_add_list_remove(tmp_path, monkeypatch):
    setup_tmp_dirs(tmp_path, monkeypatch)
    movie = {"id": 101, "title": "Fav Movie", "release_date": "2020-01-01"}
    ok = storage.save_favorite(movie)
    assert ok is True
    favs = storage.list_favorites()
    assert isinstance(favs, list) and len(favs) == 1
    assert favs[0].get("id") == 101
    ok2 = storage.save_favorite(movie)
    assert ok2 is True
    favs2 = storage.list_favorites()
    assert len(favs2) == 1
    removed = storage.remove_favorite(101)
    assert removed is True
    favs3 = storage.list_favorites()
    assert favs3 == []
    assert storage.remove_favorite(9999) is False

def test_favorites_dedup_by_title_when_no_id(tmp_path, monkeypatch):
    setup_tmp_dirs(tmp_path, monkeypatch)
    m1 = {"title": "Unique", "release_date": "1999-09-09"}
    m2 = {"title": "Unique", "release_date": "1999-09-09"}
    assert storage.save_favorite(m1) is True
    assert storage.save_favorite(m2) is True
    favs = storage.list_favorites()
    assert len(favs) == 1