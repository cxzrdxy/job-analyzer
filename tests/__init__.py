"""测试公共配置与路径常量."""
from __future__ import annotations

import sys
from pathlib import Path

# 让 tests/ 下脚本可直接 import app.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
OUTPUT_DIR = TESTS_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# 测试用 LLM 设置:允许通过环境变量覆盖
DEFAULT_LLM_PROVIDER = "deepseek"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"