import os
import json
import time
import shutil
import logging
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# 常量：基于项目 data 目录创建缓存与收藏文件
_CACHE_SUBDIR = Path("data") / "cache"
_FAVORITES_FILE = Path("data") / "favorites.json"

logger = logging.getLogger(__name__)

def ensure_data_dir(path: str = "data") -> None:
    """
    确保目录存在。
    """
    Path(path).mkdir(parents=True, exist_ok=True)

def _atomic_write_json(dest: Path, data: Any, tmp_dir: Optional[Path] = None) -> None:
    dir_for_tmp = tmp_dir or dest.parent
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, dir=str(dir_for_tmp), prefix=".tmp_", suffix=".json") as tf:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.flush()
        try:
            os.fsync(tf.fileno())
        except Exception:
            pass
        tmp_name = tf.name
    # 用 move 做原子替换（Windows 也兼容）
    shutil.move(tmp_name, str(dest))


def save_json(path: str, data: Any, *, make_backup: bool = True, retries: int = 2, retry_delay: float = 0.1) -> bool:
    """
    原子地保存 JSON。失败时记录日志，并尝试从备份恢复（若开启备份）。
    返回 True/False。
    """
    try:
        dest = Path(path)
        ensure_data_dir(str(dest.parent))
        backup_path = dest.with_suffix(dest.suffix + ".bak") if make_backup else None

        # 先做备份（若目标存在）
        if backup_path and dest.exists():
            try:
                shutil.copy2(str(dest), str(backup_path))
            except Exception:
                logger.exception("创建备份失败，继续写入：%s", backup_path)

        last_exc = None
        for attempt in range(retries + 1):
            try:
                _atomic_write_json(dest, data)
                return True
            except Exception as e:
                last_exc = e
                logger.exception("写入 JSON 失败（尝试 %d/%d）: %s", attempt + 1, retries + 1, e)
                time.sleep(retry_delay)

        # 所有重试失败，尝试恢复备份
        if backup_path and backup_path.exists():
            try:
                shutil.move(str(backup_path), str(dest))
                logger.error("写入失败，已从备份恢复：%s", backup_path)
            except Exception:
                logger.exception("写入失败且恢复备份也失败")
        return False
    except Exception as e:
        logger.exception("save_json 中发生不可预期错误: %s", e)
        return False


def load_json(path: str) -> Optional[Any]:
    """
    读取 JSON，若解析失败并存在备份则尝试从备份恢复并返回备份内容。
    失败返回 None（并记录日志）。
    """
    try:
        p = Path(path)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.exception("JSON 解析失败，尝试从备份恢复：%s", p)
            bak = p.with_suffix(p.suffix + ".bak")
            if bak.exists():
                try:
                    with bak.open("r", encoding="utf-8") as bf:
                        data = json.load(bf)
                    # 恢复备份到主文件
                    shutil.copy2(str(bak), str(p))
                    return data
                except Exception:
                    logger.exception("从备份读取也失败：%s", bak)
            return None
        except Exception:
            logger.exception("读取 JSON 文件失败：%s", p)
            return None
    except Exception as e:
        logger.exception("load_json 中发生错误: %s", e)
        return None


def is_cache_expired(path: str, ttl_seconds: int) -> bool:
    """
    基于文件修改时间判断缓存是否过期；不存在视为过期。
    """
    try:
        p = Path(path)
        if not p.exists():
            return True
        mtime = p.stat().st_mtime
        return (time.time() - mtime) > float(ttl_seconds)
    except Exception:
        logger.exception("判断缓存过期时出错：%s", path)
        return True
    
def _make_hash_for_params(params: Dict[str, Any]) -> str:
    """基于 params 生成稳定哈希（用于文件名）。"""
    try:
        raw = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    except Exception:
        raw = str(params)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def make_cache_path_for_query(params: Dict[str, Any]) -> str:
    """
    基于 params 生成缓存文件路径（data/cache/cache_<sha1>.json）。
    仅追加/兼容当前实现，不修改已有行为。
    """
    try:
        ensure_data_dir("data")
    except Exception:
        pass
    try:
        _CACHE_SUBDIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    h = _make_hash_for_params(params)
    return str(_CACHE_SUBDIR / f"cache_{h}.json")

def save_json_for_query(params: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """
    将 payload 保存为针对 params 的缓存文件（覆盖），返回写入是否成功。
    """
    try:
        path = make_cache_path_for_query(params)
        return save_json(path, payload)
    except Exception:
        logger.exception("save_json_for_query 失败")
        return False

def load_json_for_query(params: Dict[str, Any], ttl_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    按 params 加载缓存。若文件不存在返回 None。
    若 ttl_seconds 提供并且缓存已过期则返回 None。
    """
    try:
        path = make_cache_path_for_query(params)
        p = Path(path)
        if not p.exists():
            return None
        if ttl_seconds is not None and ttl_seconds >= 0:
            try:
                if is_cache_expired(path, ttl_seconds):
                    return None
            except Exception:
                return None
        return load_json(path)
    except Exception:
        logger.exception("load_json_for_query 失败")
        return None

# Favorites 管理（基于 data/favorites.json），不替换已有 save_json/load_json
def _ensure_favorites_file() -> None:
    try:
        ensure_data_dir("data")
    except Exception:
        pass
    try:
        _FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if not _FAVORITES_FILE.exists():
        try:
            save_json(str(_FAVORITES_FILE), [])
        except Exception:
            pass

def list_favorites() -> list:
    """
    返回收藏列表（若文件不存在返回空列表）。
    """
    _ensure_favorites_file()
    data = load_json(str(_FAVORITES_FILE))
    return data if isinstance(data, list) else []

def save_favorite(movie: Dict[str, Any]) -> bool:
    """
    将 movie 添加到 favorites.json（按 id 去重；无 id 则按 title+release_date 去重）。
    返回 True 表示已保存或已存在，False 表示失败。
    """
    if not isinstance(movie, dict):
        return False
    _ensure_favorites_file()
    try:
        favs = list_favorites()
        mid = movie.get("id")
        if mid is not None:
            for f in favs:
                if f.get("id") == mid:
                    return True
        else:
            key = (movie.get("title") or "") + "|" + str(movie.get("release_date") or "")
            for f in favs:
                if (f.get("title") or "") + "|" + str(f.get("release_date") or "") == key:
                    return True
        m = dict(movie)
        m["_saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        favs.append(m)
        return save_json(str(_FAVORITES_FILE), favs)
    except Exception:
        logger.exception("保存 favorite 失败")
        return False

def remove_favorite(movie_id: Any) -> bool:
    """
    按 id 删除收藏；返回是否删除成功（True 表示存在并删除了）。
    """
    if movie_id is None:
        return False
    _ensure_favorites_file()
    try:
        favs = list_favorites()
        new = [f for f in favs if f.get("id") != movie_id]
        if len(new) == len(favs):
            return False
        return save_json(str(_FAVORITES_FILE), new)
    except Exception:
        logger.exception("删除 favorite 失败")
        return False