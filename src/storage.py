import os
import json
import tempfile
import shutil
import logging
import time
from pathlib import Path
from typing import Any, Optional

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