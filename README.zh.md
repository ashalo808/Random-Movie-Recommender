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

## 未来改进（短期优先）

后续迭代将优先提升用户体验、可靠性与常用功能，短期计划如下：

1. 类型过滤与模糊匹配（优先级：高）
   - 支持用户按类型（中文/英文）筛选推荐。
   - 优先使用 TMDb 的 genre list 做 name→id 映射；不可用时在 movie.genres、genre_ids、title、overview 中做模糊匹配。
   - 交互：首次可输入类型，运行时可用 g 命令设置/取消。
   - 验收：已知类型只从匹配结果中推荐；未知类型提示并回退。

2. 单元测试与 CI（优先级：高）
   - 为 storage、recommenders、utils、类型过滤等关键模块补充单元测试。
   - 使用请求模拟（responses / requests-mock）模拟 TMDb 接口。
   - 添加 GitHub Actions 在 push/PR 时运行 pytest。
   - 验收：CI 成功运行测试，核心逻辑有单元覆盖。

3. 更智能的缓存（按查询缓存）（优先级：中）
   - 按查询参数与页码生成缓存分片（hash 命名），避免不同查询共用单一缓存。
   - 保留 TTL，支持手动清理与强制刷新（r 命令）。
   - 验收：不同查询生成不同缓存文件；强制刷新可绕过缓存。

4. 收藏（持久化用户偏好）（优先级：中）
   - 允许用户将推荐保存为本地收藏（data/favorites.json），并支持列出/删除/导入/导出。
   - 交互命令示例：`f` 保存当前，`fav-list` 列表，`fav-remove` 删除。
   - 验收：收藏持久化，能导出/导入 JSON。

## 贡献
欢迎提交 issue 或 PR。请在 PR 中说明改动目的并附带单元测试（如适用）。

## 许可证
MIT
