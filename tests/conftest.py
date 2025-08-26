import sys
from pathlib import Path

# 将项目根目录加入 sys.path（确保 tests 能导入 src 包）
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))