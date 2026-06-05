"""LangGraph 工作流编排.

流程:
    parse_resume
        ↓
    parse_job
        ↓
    skill_gap / experience / keywords
        ↓
    aggregate_report
        ↓
    generate_suggestions -> END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.workflow.nodes import (
    aggregate_report_node,
    analyze_experience_node,
    analyze_keywords_node,
    analyze_skill_gap_node,
    generate_suggestions_node,
    parse_job_node,
    parse_resume_node,
)
from app.workflow.state import AgentState

_FAN_IN = "aggregate_report"


def build_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("parse_resume", parse_resume_node)
    workflow.add_node("parse_job", parse_job_node)
    workflow.add_node("skill_gap", analyze_skill_gap_node)
    workflow.add_node("experience", analyze_experience_node)
    workflow.add_node("keywords", analyze_keywords_node)
    workflow.add_node(_FAN_IN, aggregate_report_node)
    workflow.add_node("generate_suggestions", generate_suggestions_node)

    workflow.set_entry_point("parse_resume")
    workflow.add_edge("parse_resume", "parse_job")
    workflow.add_edge("parse_job", "skill_gap")
    workflow.add_edge("parse_job", "experience")
    workflow.add_edge("parse_job", "keywords")

    # 汇总
    workflow.add_edge("skill_gap", _FAN_IN)
    workflow.add_edge("experience", _FAN_IN)
    workflow.add_edge("keywords", _FAN_IN)

    workflow.add_edge(_FAN_IN, "generate_suggestions")
    workflow.add_edge("generate_suggestions", END)

    return workflow.compile()
