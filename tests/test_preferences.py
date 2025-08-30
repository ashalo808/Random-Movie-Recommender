import os
import json
import pytest
import tempfile
from unittest.mock import patch
from src.preferences import (
    load_preferences, save_preferences, validate_preferences,
    create_default_preferences_if_missing, DEFAULT_PREFERENCES
)

@pytest.fixture
def temp_config_dir():
    """创建临时配置目录进行测试"""
    orig_dir = os.environ.get("CONFIG_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CONFIG_DIR"] = tmpdir
        yield tmpdir
    if orig_dir:
        os.environ["CONFIG_DIR"] = orig_dir
    else:
        os.environ.pop("CONFIG_DIR", None)

def test_create_default_preferences(temp_config_dir):
    """测试创建默认偏好文件"""
    with patch("src.preferences.CONFIG_DIR", temp_config_dir):
        with patch("src.preferences.PREFS_FILE", os.path.join(temp_config_dir, "preferences.json")):
            # 第一次应该成功创建
            assert create_default_preferences_if_missing() is True
            
            # 文件应该存在
            assert os.path.exists(os.path.join(temp_config_dir, "preferences.json"))
            
            # 第二次应该不做任何改动
            assert create_default_preferences_if_missing() is False

def test_load_preferences(temp_config_dir):
    """测试加载偏好"""
    with patch("src.preferences.CONFIG_DIR", temp_config_dir):
        prefs_file = os.path.join(temp_config_dir, "preferences.json")
        with patch("src.preferences.PREFS_FILE", prefs_file):
            # 不存在时应返回默认值
            loaded = load_preferences()
            assert loaded == DEFAULT_PREFERENCES
            
            # 保存自定义值
            custom = {"weights": {"popularity": 0.8, "rating": 0.1, "freshness": 0.1}, "temperature": 5.0}
            with open(prefs_file, "w") as f:
                json.dump(custom, f)
                
            # 加载应该返回与默认合并的结果
            loaded = load_preferences()
            assert loaded["weights"]["popularity"] == 0.8
            assert loaded["temperature"] == 5.0
            # 应该保留默认配置中的其他字段
            assert "temporal_balance" in loaded

def test_validate_preferences():
    """测试偏好验证"""
    # 验证权重归一化
    prefs = {"weights": {"popularity": 0.2, "rating": 0.2, "freshness": 0.1}}
    valid = validate_preferences(prefs)
    total = sum(valid["weights"].values())
    assert abs(total - 1.0) < 0.001  # 总和应该是1
    
    # 验证范围限制
    prefs = {"temperature": 20.0, "temporal_balance_strength": 10.0}
    valid = validate_preferences(prefs)
    assert valid["temperature"] <= 10.0  # 应该被限制在最大值内
    assert valid["temporal_balance_strength"] <= 5.0