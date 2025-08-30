# 随机电影推荐器 (Random Movie Recommender)

[Read in English](./README.md)

一个基于 Flask 的 Web 应用，从 TMDb API 获取电影数据，进行随机推荐，支持缓存、收藏和类型过滤。适合学习 API 调用、推荐算法和 Web 开发。

## 主要功能
- 随机推荐电影（单片/批量，支持类型过滤）
- 显示电影详情（片名、年份、评分、类型、简介）
- 本地缓存以减少 API 请求
- Web 界面：下拉选择类型、推荐按钮、收藏管理
- 持久化收藏（存储在 data/favorites.json）

## 要求
- Python 3.8+
- Flask
- requests

## 安装
在项目根目录运行（推荐使用 venv）：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt    # 若无 requirements.txt，则 pip install flask requests
```

## 配置 API Key
程序使用 TMDb API。获取 Key 后设置环境变量：

### 获取 TMDB API 密钥：
访问 [TMDB 网站](https://www.themoviedb.org/)，注册并生成 API 密钥（v3 auth key）。

### 在终端中设置环境变量并运行：
1. 停止当前应用（按 Ctrl+C）。
2. 在 PowerShell 中运行：
   ```
   $env:TMDB_API_KEY = "YOUR_API_KEY_HERE"
   python app.py
   ```
3. 或在 CMD 中运行：
   ```
   set TMDB_API_KEY=YOUR_API_KEY_HERE
   python app.py
   ```
4. 将 `YOUR_API_KEY_HERE` 替换为您的实际密钥。

### 验证：
- 应用重启后，访问 http://localhost:5000。
- 检查终端是否仍有警告。如果仍有问题，请确认密钥正确，并尝试刷新页面或点击“🔄 刷新数据”按钮。
- 如果您希望永久设置（不每次运行都输入），请在 Windows 系统环境变量中添加 `TMDB_API_KEY`。如果仍有问题，提供更多终端输出。

> 优先使用环境变量，避免将 Key 提交到版本库。

## 运行
在激活的虚拟环境中直接执行：
```powershell
python app.py
```
然后在浏览器中访问 http://localhost:5000 使用 Web 界面。

## 测试
项目包含 pytest 测试用例（tests/）。运行：
```powershell
pip install pytest
python -m pytest -q
```

## 项目结构
```
Random Movie Recommender/
├─ data/                      # 缓存数据和收藏（favorites.json）
├─ src/
│  ├─ api_client.py          # TMDb API 客户端
│  ├─ requester.py           # 请求封装
│  ├─ endpoints.py           # API 端点处理
│  ├─ factory.py             # 客户端工厂
│  ├─ storage.py             # 数据存储与缓存
│  ├─ recommenders.py        # 推荐算法
│  ├─ utils.py               # 工具函数（格式化、过滤等）
│  ├─ preferences.py         # 用户偏好设置
│  ├─ retry_policy.py        # 重试策略
├─ tests/                     # 单元测试
│  ├─ test_api.py
│  ├─ test_endpoints.py
│  ├─ test_factory.py
│  ├─ test_recommenders.py
│  ├─ test_storage.py
│  ├─ test_utils.py
│  └─ conftest.py
├─ app.py                     # Flask 后端应用
├─ index.html                 # Web 前端界面
├─ config.py (可选)           # 配置（可选）
└─ README.md
```

## 常见问题
- 下拉菜单无选项：确认 TMDB_API_KEY 已正确设置，检查终端输出是否有 500 错误。
- 推荐结果重复：检查缓存策略，确保随机页与查询参数正确。
- API 请求失败：确认网络/代理与 TMDB_API_KEY 是否正确。

## 贡献
欢迎提交 issue 或 PR。请在 PR 中说明改动目的并附带单元测试。

## 许可证
MIT