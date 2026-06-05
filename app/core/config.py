"""应用配置加载.

设计目标:
- 通过环境变量集中管理 LLM、上传、运行参数
- 提供类型安全的 Settings 对象,避免到处散落的 os.getenv
- 区分必填与可选,缺失必填项时给出明确错误
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _env_str(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """读取字符串环境变量,支持必填校验."""
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"环境变量 {key} 未配置")
    return value


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"环境变量 {key} 不是合法整数: {raw}") from exc


def _env_list(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _default_base_url(provider: str) -> Optional[str]:
    """provider → 默认 OpenAI 兼容 base_url 映射.

    - deepseek: DeepSeek 官方 OpenAI 兼容端点
    - 其他: None,沿用 ChatOpenAI 内置默认
    """
    mapping = {
        "deepseek": "https://api.deepseek.com",
    }
    return mapping.get((provider or "").lower())


@dataclass
class LLMSettings:
    """LLM 相关配置."""

    provider: str = field(default_factory=lambda: _env_str("LLM_PROVIDER", "openai") or "openai")
    model: str = field(default_factory=lambda: _env_str("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    api_key: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)
    temperature: float = 0.2
    timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 60))

    def __post_init__(self) -> None:
        # provider 决定优先读取的密钥名,缺省回退到 OPENAI_API_KEY 兼容老配置
        provider = (self.provider or "").lower()
        primary_key = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
        self.api_key = self.api_key or _env_str(primary_key) or _env_str("OPENAI_API_KEY")
        # base_url 显式 > LLM_BASE_URL > provider 默认
        self.base_url = self.base_url or _env_str("LLM_BASE_URL") or _default_base_url(provider)


@dataclass
class UploadSettings:
    """文件上传相关配置."""

    upload_dir: str = field(default_factory=lambda: _env_str("UPLOAD_DIR", "./uploads") or "./uploads")
    max_size_mb: int = field(default_factory=lambda: _env_int("UPLOAD_MAX_MB", 10))
    allowed_extensions: List[str] = field(
        default_factory=lambda: _env_list("UPLOAD_ALLOWED_EXTS", [".pdf", ".docx", ".txt"])
    )
    auto_cleanup: bool = True


@dataclass
class AppSettings:
    """应用聚合配置."""

    app_name: str = "求职分析智能体"
    version: str = "0.1.0"
    debug: bool = field(default_factory=lambda: _env_str("APP_DEBUG", "false") == "true")
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO") or "INFO")
    llm: LLMSettings = field(default_factory=LLMSettings)
    upload: UploadSettings = field(default_factory=UploadSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """提供进程内单例配置."""
    return AppSettings()
