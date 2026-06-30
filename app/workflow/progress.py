"""流式分析进度定义(单一事实源).

前后端共用:
- STAGES: 阶段表,定义 8 个分析阶段的 key / label / percent 区间
- ProgressEvent: NDJSON 行格式 TypedDict
- stage_by_node(): LangGraph 节点名 → StageDef 映射

线程安全:
- LangGraph astream() 在线程池中执行同步节点,ContextVar 无法跨线程传播
- 因此使用 _shared 系列函数,用 threading.Lock 保护模块级变量
- LLMClient 在工作线程中通过 _shared 函数获取回调与当前阶段
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional


# ---- 线程安全的共享变量 ----
# LangGraph astream() 在线程池中执行同步节点,
# 用模块级变量 + threading.Lock 作为跨线程通信机制。

_progress_shared_lock = threading.Lock()
_progress_shared: Optional[Callable[[str, dict[str, Any]], None]] = None

_stage_shared_lock = threading.Lock()
_stage_shared: Optional["StageDef"] = None


def set_progress_callback(cb: Optional[Callable[[str, dict[str, Any]], None]]) -> None:
    """线程安全:设置全局进度回调(供 LLMClient 在工作线程中读取)."""
    global _progress_shared
    with _progress_shared_lock:
        _progress_shared = cb


def get_progress_callback() -> Optional[Callable[[str, dict[str, Any]], None]]:
    """线程安全:获取全局进度回调."""
    with _progress_shared_lock:
        return _progress_shared


def set_current_stage(stage: Optional["StageDef"]) -> None:
    """线程安全:设置当前阶段(供节点函数在工作线程中设置)."""
    global _stage_shared
    with _stage_shared_lock:
        _stage_shared = stage


def get_current_stage() -> Optional["StageDef"]:
    """线程安全:获取当前阶段."""
    with _stage_shared_lock:
        return _stage_shared


@dataclass(frozen=True)
class StageDef:
    """单个阶段定义."""

    index: int
    key: str
    label: str
    percent_start: float
    percent_end: float
    is_llm: bool

    @property
    def span(self) -> tuple[float, float]:
        return (self.percent_start, self.percent_end)

    @property
    def quarter(self) -> float:
        """区间 1/4 处(stage_start 默认 percent)."""
        return self.percent_start + (self.percent_end - self.percent_start) * 0.25

    @property
    def half(self) -> float:
        """区间 1/2 处(first_token 默认 percent)."""
        return self.percent_start + (self.percent_end - self.percent_start) * 0.5


# ---- 阶段表(与文档 §3.2 一致) ----
STAGES: tuple[StageDef, ...] = (
    StageDef(0, "upload", "接收并解析文件", 0, 5, False),
    StageDef(1, "parse_resume", "解析简历结构", 5, 20, True),
    StageDef(2, "parse_job", "解析岗位要求", 20, 35, True),
    StageDef(3, "skill_gap", "匹配技能差距", 35, 65, True),
    StageDef(4, "experience", "评估经验匹配", 65, 78, False),
    StageDef(5, "keywords", "比对关键词", 78, 88, False),
    StageDef(6, "aggregate", "汇总诊断报告", 88, 92, False),
    StageDef(7, "suggestions", "生成优化建议", 92, 99, True),
)

# LangGraph 节点名 → StageDef 索引映射
_NODE_TO_STAGE_KEY: dict[str, str] = {
    "parse_resume": "parse_resume",
    "parse_job": "parse_job",
    "skill_gap": "skill_gap",
    "experience": "experience",
    "keywords": "keywords",
    "aggregate_report": "aggregate",
    "generate_suggestions": "suggestions",
}


def stage_by_node(node_name: str) -> Optional[StageDef]:
    """根据 LangGraph 节点名返回对应的 StageDef."""
    key = _NODE_TO_STAGE_KEY.get(node_name)
    if key is None:
        return None
    for s in STAGES:
        if s.key == key:
            return s
    return None


def stage_by_key(key: str) -> Optional[StageDef]:
    """根据阶段 key 返回 StageDef."""
    for s in STAGES:
        if s.key == key:
            return s
    return None


# ---- NDJSON 事件类型(TypedDict 风格,用于文档和类型提示) ----
# 实际使用时直接构造 dict 即可,不强制类型检查


def make_meta_event(trace_id: str) -> dict[str, Any]:
    """构建 meta 事件行."""
    return {
        "type": "meta",
        "trace_id": trace_id,
        "stages": [
            {"index": s.index, "key": s.key, "label": s.label, "span": [s.percent_start, s.percent_end]}
            for s in STAGES
        ],
    }


def make_stage_start_event(stage: StageDef) -> dict[str, Any]:
    """构建 stage_start 事件行."""
    return {
        "type": "stage_start",
        "index": stage.index,
        "key": stage.key,
        "label": stage.label,
        "percent": stage.quarter if stage.is_llm else ((stage.percent_start + stage.percent_end) / 2),
    }


def make_progress_event(
    stage: StageDef,
    percent: float,
    message: str = "",
    chars: int = 0,
) -> dict[str, Any]:
    """构建 progress 事件行(percent 在阶段区间内线性插值)."""
    clamped = max(stage.percent_start, min(percent, stage.percent_end))
    evt: dict[str, Any] = {
        "type": "progress",
        "index": stage.index,
        "percent": round(clamped, 1),
    }
    if message:
        evt["message"] = message
    if chars:
        evt["chars"] = chars
    return evt


def make_stage_end_event(stage: StageDef) -> dict[str, Any]:
    """构建 stage_end 事件行."""
    return {
        "type": "stage_end",
        "index": stage.index,
        "key": stage.key,
    }


def make_done_event(data: dict[str, Any], duration_ms: float) -> dict[str, Any]:
    """构建 done 事件行."""
    return {
        "type": "done",
        "data": data,
        "duration_ms": round(duration_ms, 0),
    }


def make_error_event(
    stage_key: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    """构建 error 事件行."""
    return {
        "type": "error",
        "stage": stage_key,
        "code": code,
        "message": message,
    }


def compute_streaming_percent(stage: "StageDef", phase: str, chars: int) -> float:
    """根据阶段、回传阶段和已接收字符数计算进度百分比.

    策略:
    - first_token: 阶段区间的 35% 处(LLM 已开始输出)
    - streaming: 从 35% 逐步逼近 90%,用 chars/1500 做归一化
    - 剩余 10% 留给 stage_end,避免进度条"卡在 99%"
    """
    span = stage.percent_end - stage.percent_start
    if phase == "first_token":
        return stage.percent_start + 0.35 * span
    if phase == "streaming":
        fraction = min(chars / 1500, 1.0)
        return stage.percent_start + (0.35 + 0.55 * fraction) * span
    return stage.percent_start + 0.1 * span


# ---- 面试题预测专用阶段(独立于主分析 STAGES,避免协议冲突) ----

INTERVIEW_STAGES: tuple[StageDef, ...] = (
    StageDef(0, "load_cache", "读取分析缓存", 0, 10, False),
    StageDef(1, "build_prompt", "构造预测 Prompt", 10, 30, False),
    StageDef(2, "predict", "LLM 生成面试题", 30, 95, True),
    StageDef(3, "validate", "校验与修正", 95, 99, False),
)

# 面试预测节点名 → 阶段 key 映射
_INTERVIEW_NODE_TO_STAGE_KEY: dict[str, str] = {
    "load_cache": "load_cache",
    "build_prompt": "build_prompt",
    "predict": "predict",
    "validate": "validate",
}


def interview_stage_by_key(key: str) -> Optional[StageDef]:
    """根据阶段 key 返回面试预测专用 StageDef."""
    for s in INTERVIEW_STAGES:
        if s.key == key:
            return s
    return None
