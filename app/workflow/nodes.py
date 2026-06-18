"""工作流节点.

每个节点只关注"输入 -> 输出",由 LangGraph 串联为整体流程.
"""
from __future__ import annotations

import json
from typing import List

from pydantic import BaseModel, Field, field_validator

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
    """汇总匹配结果,通过 LLM 综合评判产出 MatchReport."""

    skill = state.get("skill_gap_partial") or {}
    experience = state.get("experience_match_partial") or {}
    keywords = state.get("keyword_match_partial") or {}
    resume = state.get("resume_data")
    job = state.get("job_requirement")

    if not resume or not job:
        raise WorkflowError("缺少简历或岗位数据,无法汇总报告")

    # LLM 综合评分
    llm_result = _llm_score(resume, job, skill, experience, keywords)

    hard_gaps: List[str] = []
    for s in skill.get("missing", []) or []:
        hard_gaps.append(f"缺少硬技能: {s.get('skill')}")

    state["match_report"] = MatchReport(
        overall_score=llm_result.overall_score,
        score_reasoning=llm_result.score_reasoning,
        strengths=llm_result.strengths,
        weaknesses=llm_result.weaknesses,
        skill_gap=skill,
        experience=experience,
        keywords=keywords,
        hard_requirements_gaps=hard_gaps,
    )
    return state


def generate_suggestions_node(state: AgentState) -> AgentState:
    resume = state.get("resume_data")
    job = state.get("job_requirement")
    report_raw = state.get("match_report")
    if not (resume and job and report_raw):
        raise WorkflowError("前置分析未完成,无法生成建议")
    # LangGraph 节点间传递时 Pydantic 模型可能被序列化为 dict，需还原
    if isinstance(report_raw, dict):
        report = MatchReport.model_validate(report_raw)
    else:
        report = report_raw
    try:
        suggestions = generate_suggestions(resume, job, report, LLMClient())
    except Exception as exc:
        logger.exception("建议生成失败,降级为启发式建议: %s", exc)
        from app.workflow.suggestion_generator import _fallback_suggestions
        suggestions = _fallback_suggestions(resume, job, report)
    state["suggestions"] = [s.model_dump() for s in suggestions]
    return state


# ============================================================
# LLM 综合评分
# ============================================================

_SCORE_SYSTEM_PROMPT = (
    "你是一名资深猎头与求职评估专家，擅长综合评估候选人与岗位的匹配程度。"
    "你需要基于已有的结构化分析结果，给出一个综合评分和详细理由。"
    "\n\n"
    "评分锚点（必须遵循）:\n"
    "- 90+: 候选人几乎完美匹配岗位，核心技能全部覆盖，经验充足，无明显短板\n"
    "- 75-89: 候选人整体匹配，大部分核心技能覆盖，经验基本满足，有少量可补足的缺口\n"
    "- 60-74: 候选人部分匹配，存在若干技能或经验缺口，需要针对性补强\n"
    "- 40-59: 候选人匹配度较低，核心技能缺失较多或经验明显不足\n"
    "- <40: 候选人与岗位严重不匹配\n"
    "\n"
    "评分要求:\n"
    "1. overall_score 必须综合考量技能、经验、关键词三个维度，不能简单取平均\n"
    "2. 核心技能缺失应比边缘技能缺失扣分更重\n"
    "3. 经验不足但技能覆盖好时，分数应高于技能缺失但经验充足\n"
    "4. 关键词覆盖反映简历表达与 JD 的语言契合度，权重低于技能和经验\n"
    "5. score_reasoning 必须说明为什么是这个分数，引用具体证据\n"
    "6. strengths 和 weaknesses 必须具体，不能泛泛而谈\n"
    "\n"
    "请严格按 JSON Schema 输出，不要追加任何解释文字或 Markdown 包装。"
)


class LLMScoreOutput(BaseModel):
    """LLM 综合评分输出."""

    overall_score: float = Field(..., description="0-100 综合匹配分")
    score_reasoning: str = Field(..., description="评分理由(2-4 句话)")
    strengths: List[str] = Field(default_factory=list, description="匹配亮点(2-3 条)")
    weaknesses: List[str] = Field(default_factory=list, description="主要短板(2-3 条)")

    @field_validator("overall_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return round(max(0.0, min(100.0, v)), 1)


def _llm_score(
    resume, job, skill: dict, experience: dict, keywords: dict
) -> LLMScoreOutput:
    """调 LLM 做综合评分,失败抛 WorkflowError."""
    user_prompt = _build_score_prompt(resume, job, skill, experience, keywords)
    try:
        result: LLMScoreOutput = LLMClient().chat_json(
            system=_SCORE_SYSTEM_PROMPT,
            user=user_prompt,
            schema=LLMScoreOutput,
            max_retries=1,
        )
    except Exception as exc:
        raise WorkflowError(f"LLM 综合评分失败: {exc}")
    return result


def _build_score_prompt(
    resume, job, skill: dict, experience: dict, keywords: dict
) -> str:
    """构造 LLM 评分 prompt."""
    # 简历摘要
    resume_info = {
        "name": getattr(resume, "name", None),
        "skills": getattr(resume, "skills", []),
        "work": [
            {
                "position": getattr(w, "position", None),
                "company": getattr(w, "company", None),
            }
            for w in (getattr(resume, "work_experience", None) or [])
        ],
    }

    # 岗位摘要
    job_info = {
        "position": getattr(job, "position", None),
        "hard_skills": [
            getattr(r, "description", "") for r in (getattr(job, "hard_skills", None) or [])
        ],
        "soft_skills": [
            getattr(r, "description", "") for r in (getattr(job, "soft_skills", None) or [])
        ],
        "experience": [
            getattr(r, "description", "") for r in (getattr(job, "experience", None) or [])
        ],
    }

    # 技能匹配
    matched_skills = [s.get("skill", "") for s in skill.get("matched", [])]
    partial_skills = [s.get("skill", "") for s in skill.get("partial", [])]
    missing_skills = [s.get("skill", "") for s in skill.get("missing", [])]

    # 经验匹配
    exp_notes = experience.get("notes", [])

    # 关键词匹配
    matched_kw = keywords.get("matched", [])
    missing_kw = keywords.get("missing", [])

    # 硬性要求差距
    hard_gaps = [
        s.get("skill", "") for s in skill.get("missing", []) if s.get("skill")
    ]

    return (
        "请基于以下分析结果，评估候选人与岗位的综合匹配度。\n\n"
        f"## 候选人摘要\n{json.dumps(resume_info, ensure_ascii=False, default=str)}\n\n"
        f"## 岗位摘要\n{json.dumps(job_info, ensure_ascii=False, default=str)}\n\n"
        f"## 技能匹配结果\n"
        f"- 已命中: {matched_skills}\n"
        f"- 部分匹配: {partial_skills}\n"
        f"- 缺失: {missing_skills}\n"
        f"- 覆盖率: {skill.get('coverage', 0.0)}\n\n"
        f"## 经验匹配结果\n"
        f"- 要求年限: {experience.get('years_required')}\n"
        f"- 估算年限: {experience.get('years_estimated')}\n"
        f"- 相关角色: {experience.get('related_roles', [])}\n"
        f"- 备注: {exp_notes}\n"
        f"- 规则评分: {experience.get('score', 0.0)}\n\n"
        f"## 关键词匹配结果\n"
        f"- 已覆盖: {matched_kw}\n"
        f"- 未覆盖: {missing_kw}\n"
        f"- 覆盖率: {keywords.get('coverage', 0.0)}\n\n"
        f"## 硬性要求差距\n{hard_gaps}\n\n"
        "请输出综合评分。"
    )

