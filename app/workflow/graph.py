"""LangGraph 工作流编排.

流程:
                  ┌─→ parse_resume ─┐
    START ────────┤                 ├─→ {skill_gap, experience, keywords} (并行) → aggregate → suggestions → END
                  └─→ parse_job  ──┘
"""
from __future__ import annotations

import time

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.core.logging import get_logger
from app.workflow.nodes import (
    aggregate_report_node,
    analyze_experience_node,
    analyze_keywords_node,
    analyze_skill_gap_node,
    generate_suggestions_node,
    parse_job_node,
    parse_resume_node,
)
from app.workflow.progress import set_current_stage_shared, stage_by_node
from app.workflow.state import AgentState

logger = get_logger(__name__)

_FAN_IN = "aggregate_report"

# 并行匹配节点列表
_PARALLEL_MATCHERS = ["skill_gap", "experience", "keywords"]

# 并行抽取节点:parse_resume 和 parse_job 互不依赖,从 START 并行启动
_PARALLEL_PARSERS = ["parse_resume", "parse_job"]


def _route_to_matchers(state: AgentState) -> list[Send]:
    """fan-out: 将状态分发到三个匹配节点并行执行."""
    return [Send(node, state) for node in _PARALLEL_MATCHERS]


def _with_stage_tracking(node_name: str, node_fn):
    """包装节点函数,在执行前设置当前阶段(线程安全)并记录耗时.

    LangGraph astream() 在线程池中执行同步节点,ContextVar 无法跨线程传播,
    因此通过 set_current_stage_shared 让进度回调能知道当前阶段.
    """
    def wrapped(state):
        stage = stage_by_node(node_name)
        if stage:
            set_current_stage_shared(stage)
        t0 = time.monotonic()
        result = node_fn(state)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("节点 %s 完成, 耗时 %.0fms", node_name, elapsed_ms)
        return result
    return wrapped


def _dispatch_matchers_node(state: AgentState) -> dict:
    """fan-in 中继节点:等待 parse_resume 和 parse_job 都完成后,透传状态.

    不做任何计算,仅作为 LangGraph fan-in 的汇聚点,
    确保 matchers 在两个抽取节点都完成后才开始执行.
    """
    return {"errors": state.get("errors", [])}


def build_workflow():
    workflow = StateGraph(AgentState)

    # ---- 节点注册 ----
    workflow.add_node("parse_resume", _with_stage_tracking("parse_resume", parse_resume_node))
    workflow.add_node("parse_job", _with_stage_tracking("parse_job", parse_job_node))
    workflow.add_node("dispatch_matchers", _with_stage_tracking("dispatch_matchers", _dispatch_matchers_node))
    workflow.add_node("skill_gap", _with_stage_tracking("skill_gap", analyze_skill_gap_node))
    workflow.add_node("experience", _with_stage_tracking("experience", analyze_experience_node))
    workflow.add_node("keywords", _with_stage_tracking("keywords", analyze_keywords_node))
    workflow.add_node(_FAN_IN, _with_stage_tracking("aggregate_report", aggregate_report_node))
    workflow.add_node("generate_suggestions", _with_stage_tracking("generate_suggestions", generate_suggestions_node))

    # ---- 边:并行抽取 ----
    # parse_resume 和 parse_job 从 START 并行启动(互不依赖)
    workflow.add_edge(START, "parse_resume")
    workflow.add_edge(START, "parse_job")

    # ---- 边:fan-in 到 dispatch_matchers ----
    # 两个抽取节点都完成后,汇聚到 dispatch_matchers
    workflow.add_edge("parse_resume", "dispatch_matchers")
    workflow.add_edge("parse_job", "dispatch_matchers")

    # ---- 边:fan-out 到三个匹配节点 ----
    workflow.add_conditional_edges("dispatch_matchers", _route_to_matchers)

    # ---- 边:fan-in 到 aggregate_report ----
    workflow.add_edge("skill_gap", _FAN_IN)
    workflow.add_edge("experience", _FAN_IN)
    workflow.add_edge("keywords", _FAN_IN)

    # ---- 边:后续 ----
    workflow.add_edge(_FAN_IN, "generate_suggestions")
    workflow.add_edge("generate_suggestions", END)

    return workflow.compile()
