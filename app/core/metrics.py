"""进程级运行时指标.

- 启动时间 / PID
- 请求计数 / 错误计数
- 最近 N 条请求日志(用于根路径展示)
所有数据均为运行时真实采集,不依赖第三方系统监控库。
"""
from __future__ import annotations

import datetime
import os
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict, List, Optional


@dataclass(frozen=True)
class RequestLog:
    ts: float
    method: str
    path: str
    status: int
    duration_ms: float


class Metrics:
    """进程内单例指标."""

    _instance: Optional["Metrics"] = None

    def __new__(cls) -> "Metrics":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._lock = Lock()
        self.started_at: float = time.time()
        self.pid: int = os.getpid()
        self.request_count: int = 0
        self.error_count: int = 0
        self.recent: Deque[RequestLog] = deque(maxlen=20)

    def record(self, method: str, path: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.request_count += 1
            if status >= 500:
                self.error_count += 1
            self.recent.append(
                RequestLog(
                    ts=time.time(),
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
            )

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def uptime_str(self) -> str:
        s = int(self.uptime_seconds)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def started_str(self) -> str:
        return datetime.datetime.fromtimestamp(self.started_at).strftime("%Y-%m-%d %H:%M:%S")

    def avg_latency_by_path(self) -> Dict[str, float]:
        """最近请求按路径聚合的平均耗时(ms)."""
        with self._lock:
            by_path: Dict[str, List[float]] = {}
            for log in self.recent:
                by_path.setdefault(log.path, []).append(log.duration_ms)
        return {p: sum(d) / len(d) for p, d in by_path.items()}

    def snapshot(self) -> Dict[str, object]:
        """线程安全的一次性快照,供模板渲染使用."""
        with self._lock:
            recent = list(self.recent)
        return {
            "started_at": self.started_at,
            "started_str": self.started_str(),
            "uptime": self.uptime_str(),
            "pid": self.pid,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "recent": recent,
            "avg_latency": self.avg_latency_by_path(),
        }


metrics = Metrics()
