"""统一日志工具.

- 控制台 + 文件双输出
- 结构化字段: 时间/级别/模块/消息
- 简单实现,不依赖第三方日志框架,方便轻量部署
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

_INITIALIZED = False


def setup_logging(log_file: Optional[str] = None) -> None:
    """初始化全局日志配置,幂等可重复调用."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    target = log_file or "app.log"
    log_path = Path(settings.upload.upload_dir).parent / "logs" / target
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
