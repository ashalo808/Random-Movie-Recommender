# 随机电影推荐器 (Random Movie Recommender)

[Read in English](./README.md)

简单的命令行工具，从电影数据库随机挑选并展示电影信息，适合作为学习 API、JSON 与随机算法的练手项目。

## 主要功能
- 随机推荐电影（单片/批量）
- 显示片名、年份、评分、类型与简介（带 emoji 提升可读性）
- 可缓存结果以减少 API 请求

## 要求
- Python 3.8+
- requests

## 安装
在项目根目录运行（推荐使用 venv）：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt    # 若无 requirements.txt，则 pip install requests
```

## 配置 API Key
程序使用 TMDb（The Movie Database）API。获取 Key 后有两种方式配置：

1. 环境变量（推荐）：
```powershell
$env:TMDB_API_KEY = "你的_api_key"
```

2. 或在项目根目录创建 `config.py`（示例）：
```python
def get_tmdb_key():
    return "你的_api_key"
```

> 优先使用环境变量，避免将 Key 提交到版本库。

## 运行
在激活的虚拟环境中直接执行：
```powershell
python main.py
```
交互说明：
- 回车：随机推荐一部
- b：批量推荐（3 个）
- r：刷新并从 API 重新获取
- q：退出

## 测试
项目包含 pytest 测试用例（tests/）。运行：
```powershell
pip install pytest
python -m pytest -q
```

## 项目结构
```
Random Movie Recommender/
├─ data/                      # 缓存数据
├─ src/
│  ├─ api_client.py
│  ├─ requester.py
│  ├─ endpoints.py
│  ├─ factory.py
│  ├─ storage.py
│  ├─ recommenders.py
│  └─ utils.py
├─ main.py
├─ config.py (可选)
└─ README.md
```

## 常见问题
- 推荐结果重复或同年代：检查 `load_or_fetch` 的分页与缓存策略，确保随机页与缓存键包含页码与查询参数。
- 无法请求 API：确认网络/代理与 TMDB_API_KEY 是否正确。

## 贡献
欢迎提交 issue 或 PR。请在 PR 中说明改动目的并附带单元测试（如适用）。

## 许可证
MIT
