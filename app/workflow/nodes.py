"""工作流节点.

每个节点只关注"输入 -> 输出",由 LangGraph 串联为整体流程.
"""
from __future__ import annotations

from typing import List

from app.core.errors import ExtractError, WorkflowError
from app.core.logging import get_logger
from app.extractors.job_extractor import JobExtractor
from app.extractors.resume_extractor import ResumeExtractor
from app.matchers.experience_matcher import analyze_experience
from app.matchers.keyword_matcher import analyze_keywords
from app.matchers.skill_matcher import analyze_skill_gap
from app.models.suggestion import MatchReport
from app.workflow.state import AgentState
from app.workflow.suggestion_generator import generate_suggestions
from app.extractors.llm_client import LLMClient

logger = get_logger(__name__)


def parse_resume_node(state: AgentState) -> AgentState:
    text = (state.get("inputs") or {}).get("resume_text") or ""
    if not text.strip():
        raise WorkflowError("简历文本为空,无法继续")
    state["resume_data"] = ResumeExtractor().extract(text)
    return state


def parse_job_node(state: AgentState) -> AgentState:
    text = (state.get("inputs") or {}).get("job_text") or ""
    if not text.strip():
        raise WorkflowError("岗位 JD 文本为空,无法继续")
    state["job_requirement"] = JobExtractor().extract(text)
    return state


def analyze_skill_gap_node(state: AgentState) -> AgentState:
    resume = state.get("resume_data")
    job = state.get("job_requirement")
    if not resume or not job:
        raise WorkflowError("缺少简历或岗位数据,无法分析技能差距")
    state["skill_gap_partial"] = analyze_skill_gap(resume, job, llm_client=LLMClient()).model_dump()
    return state


def analyze_experience_node(state: AgentState) -> AgentState:
    resume = state.get("resume_data")
    job = state.get("job_requirement")
    if not resume or not job:
        raise WorkflowError("缺少简历或岗位数据,无法分析经验")
    state["experience_match_partial"] = analyze_experience(resume, job).model_dump()
    return state


def analyze_keywords_node(state: AgentState) -> AgentState:
    resume = state.get("resume_data")
    job = state.get("job_requirement")
    if not resume or not job:
        raise WorkflowError("缺少简历或岗位数据,无法分析关键词")
    state["keyword_match_partial"] = analyze_keywords(resume, job).model_dump()
    return state


def aggregate_report_node(state: AgentState) -> AgentState:
    """汇总匹配结果,产出 MatchReport."""

    skill = state.get("skill_gap_partial") or {}
    experience = state.get("experience_match_partial") or {}
    keywords = state.get("keyword_match_partial") or {}

    skill_coverage = float(skill.get("coverage", 0.0))
    exp_score = float(experience.get("score", 0.0))
    kw_coverage = float(keywords.get("coverage", 0.0))

    overall = round(100 * (0.5 * skill_coverage + 0.3 * exp_score + 0.2 * kw_coverage), 1)

    hard_gaps: List[str] = []
    for s in skill.get("missing", []) or []:
        hard_gaps.append(f"缺少硬技能: {s.get('skill')}")

    state["match_report"] = MatchReport(
        overall_score=overall,
        skill_gap=skill,
        experience=experience,
        keywords=keywords,
        hard_requirements_gaps=hard_gaps,
    )
    return state


def generate_suggestions_node(state: AgentState) -> AgentState:
    resume = state.get("resume_data")
    job = state.get("job_requirement")
    report = state.get("match_report")
    if not (resume and job and report):
        raise WorkflowError("前置分析未完成,无法生成建议")
    try:
        suggestions = generate_suggestions(resume, job, report, LLMClient())
    except ExtractError as exc:
        logger.warning("建议生成失败,降级为启发式建议: %s", exc)
        suggestions = _fallback_suggestions(resume, job, report)
    state["suggestions"] = [s.model_dump() for s in suggestions]
    return state


def _fallback_suggestions(resume, job, report: MatchReport) -> list:
    """当 LLM 输出失败时,基于匹配结果给出保守建议."""

    from app.models.suggestion import ResumeSection, ResumeSuggestion, SuggestionPriority, SuggestionType

    items: list[ResumeSuggestion] = []
    for skill in report.skill_gap.missing:
        items.append(
            ResumeSuggestion(
                type=SuggestionType.CONTENT,
                priority=SuggestionPriority.HIGH,
                section=ResumeSection.SKILLS,
                suggestion=f"在技能列表中补充 {skill.skill},并提供使用场景",
                reason=f"岗位硬性要求中明确需要 {skill.skill}",
                related_jd_requirement=skill.skill,
            )
        )
    for kw in report.keywords.missing:
        items.append(
            ResumeSuggestion(
                type=SuggestionType.KEYWORD,
                priority=SuggestionPriority.MEDIUM,
                section=ResumeSection.OVERALL,
                suggestion=f"在项目或工作经历描述中自然融入关键词 {kw}",
                reason=f"JD 高频关键词 {kw} 未在简历中出现",
                related_jd_requirement=kw,
            )
        )
    for note in report.experience.notes:
        items.append(
            ResumeSuggestion(
                type=SuggestionType.QUANTIFY,
                priority=SuggestionPriority.MEDIUM,
                section=ResumeSection.WORK_EXPERIENCE,
                suggestion="用具体年限、项目规模、业绩数字补强工作经历",
                reason=note,
            )
        )
    return items
