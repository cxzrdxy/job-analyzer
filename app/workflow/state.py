"""工作流状态定义.

按"原始输入 -> 解析结果 -> 分析结果 -> 建议"分层,避免状态自相矛盾.
"""
from __future__ import annotations

from typing import Annotated, Any, List, Optional, TypedDict

from app.models.job_requirement import JobRequirement
from app.models.resume import ResumeData
from app.models.suggestion import MatchReport, ResumeSuggestion


class AnalyzeInput(TypedDict, total=False):
    """请求侧输入,可以是文本或文件路径."""

    resume_text: Optional[str]
    job_text: Optional[str]
    trace_id: Optional[str]


class AnalyzeOutput(TypedDict, total=False):
    """最终响应需要的数据."""

    match_report: MatchReport
    suggestions: List[ResumeSuggestion]


def _keep_last(_current, new):
    """LangGraph reducer:多源写入时保留最后一个值."""
    return new


class AgentState(TypedDict, total=False):
    """LangGraph 状态.

    设计原则:
    - 必填字段在节点执行后填入,允许运行初期为空
    - 解析/匹配结果同时持有原始数据,便于审计与重试
    """

    # 输入
    inputs: Annotated[AnalyzeInput, _keep_last]

    # 中间结果
    resume_data: Annotated[Optional[ResumeData], _keep_last]
    job_requirement: Annotated[Optional[JobRequirement], _keep_last]

    skill_gap_partial: Annotated[Optional[dict], _keep_last]
    experience_match_partial: Annotated[Optional[dict], _keep_last]
    keyword_match_partial: Annotated[Optional[dict], _keep_last]
    match_report: Annotated[Optional[MatchReport], _keep_last]

    # 最终输出
    suggestions: Annotated[List[dict[str, Any]], _keep_last]
    errors: Annotated[List[str], _keep_last]
