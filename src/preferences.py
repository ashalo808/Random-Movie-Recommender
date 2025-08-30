import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认偏好设置
DEFAULT_PREFERENCES = {
    "weights": {
        "popularity": 0.3,
        "rating": 0.3,
        "freshness": 0.4
    },
    "temperature": 3.0,
    "temporal_balance": True,
    "temporal_balance_strength": 1.5,
    "diversify_by": "genre",  # 可选: None, "genre", "year", "director"
    "max_items_per_genre": 2,  # 批量推荐时每个类型最多出现次数
}

CONFIG_DIR = "config"
PREFS_FILE = os.path.join(CONFIG_DIR, "preferences.json")

def ensure_config_dir():
    """确保配置目录存在"""
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            logger.info(f"创建配置目录: {CONFIG_DIR}")
        except Exception as e:
            logger.error(f"无法创建配置目录 {CONFIG_DIR}: {e}")
            return False
    return True

def load_preferences() -> Dict[str, Any]:
    """加载用户偏好，若不存在则返回默认值"""
    if not os.path.exists(PREFS_FILE):
        logger.info(f"偏好文件不存在，使用默认配置: {PREFS_FILE}")
        return DEFAULT_PREFERENCES.copy()
    
    try:
        with open(PREFS_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
            logger.info(f"成功加载偏好文件: {PREFS_FILE}")
            
            # 确保所有默认键都存在（避免旧版本文件缺少新字段）
            for key, value in DEFAULT_PREFERENCES.items():
                if key not in prefs:
                    prefs[key] = value
                    logger.debug(f"使用默认值填充缺失字段: {key}={value}")
                    
            # 确保权重字段完整
            if "weights" in prefs and isinstance(prefs["weights"], dict):
                for weight_key, weight_val in DEFAULT_PREFERENCES["weights"].items():
                    if weight_key not in prefs["weights"]:
                        prefs["weights"][weight_key] = weight_val
                        
            return prefs
    except Exception as e:
        logger.error(f"加载偏好文件失败 {PREFS_FILE}: {e}")
        return DEFAULT_PREFERENCES.copy()

def save_preferences(prefs: Dict[str, Any]) -> bool:
    """保存用户偏好到文件"""
    if not ensure_config_dir():
        return False
        
    try:
        with open(PREFS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
        logger.info(f"偏好已保存至: {PREFS_FILE}")
        return True
    except Exception as e:
        logger.error(f"保存偏好失败: {e}")
        return False

def validate_preferences(prefs: Dict[str, Any]) -> Dict[str, Any]:
    """验证并修复偏好配置，确保值在合理范围内"""
    valid = DEFAULT_PREFERENCES.copy()
    
    try:
        # 验证权重
        if "weights" in prefs and isinstance(prefs["weights"], dict):
            for k, v in prefs["weights"].items():
                if k in valid["weights"] and isinstance(v, (int, float)):
                    valid["weights"][k] = max(0.0, min(1.0, float(v)))
                    
            # 确保权重总和为 1.0
            total = sum(valid["weights"].values())
            if total > 0:
                for k in valid["weights"]:
                    valid["weights"][k] /= total
        
        # 验证 temperature
        if "temperature" in prefs and isinstance(prefs["temperature"], (int, float)):
            valid["temperature"] = max(0.0, min(10.0, float(prefs["temperature"])))
            
        # 验证布尔值
        if "temporal_balance" in prefs:
            valid["temporal_balance"] = bool(prefs["temporal_balance"])
            
        # 验证 strength
        if "temporal_balance_strength" in prefs and isinstance(prefs["temporal_balance_strength"], (int, float)):
            valid["temporal_balance_strength"] = max(0.0, min(5.0, float(prefs["temporal_balance_strength"])))
            
        # 验证分类方式
        if "diversify_by" in prefs and prefs["diversify_by"] in (None, "genre", "year", "director"):
            valid["diversify_by"] = prefs["diversify_by"]
            
        # 验证每类型最大条目数
        if "max_items_per_genre" in prefs and isinstance(prefs["max_items_per_genre"], int):
            valid["max_items_per_genre"] = max(1, min(10, int(prefs["max_items_per_genre"])))
            
    except Exception as e:
        logger.warning(f"验证偏好时出错，使用默认值: {e}")
        
    return valid

def get_effective_preferences(override_prefs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """获取有效偏好，允许通过参数覆盖保存的配置"""
    base_prefs = load_preferences()
    
    if not override_prefs:
        return validate_preferences(base_prefs)
        
    # 合并覆盖参数
    merged = dict(base_prefs)
    for key, value in override_prefs.items():
        if key == "weights" and isinstance(value, dict) and isinstance(merged.get("weights"), dict):
            # 合并权重子字典
            for w_key, w_value in value.items():
                merged["weights"][w_key] = w_value
        else:
            merged[key] = value
            
    return validate_preferences(merged)

def create_default_preferences_if_missing() -> bool:
    """如果偏好文件不存在，创建默认值"""
    if os.path.exists(PREFS_FILE):
        return False
        
    if ensure_config_dir():
        return save_preferences(DEFAULT_PREFERENCES)
    return False