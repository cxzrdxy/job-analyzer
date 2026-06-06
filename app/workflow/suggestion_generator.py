"""建议生成器.

- 输入: 简历 + 岗位 + 匹配分析结果(综合证据)
- 输出: List[ResumeSuggestion],按 priority / type 排序
- 设计原则: 给模型"已结构化的证据"而非"自由发挥",降低幻觉
"""
from __future__ import annotations

import json
from typing import List

from pydantic import TypeAdapter

from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.job_requirement import JobRequirement
from app.models.resume import ResumeData
from app.models.suggestion import (
    MatchReport,
    ResumeSection,
    ResumeSuggestion,
    SuggestionPriority,
    SuggestionType,
)

logger = get_logger(__name__)

_SUGGESTION_ADAPTER = TypeAdapter(List[ResumeSuggestion])


_SYSTEM_PROMPT = (
    "你是资深求职教练,根据给定的简历、岗位、匹配证据,生成**可执行**的简历修改建议。"
    "建议必须具体到段落、要点、量化方式,不要泛泛而谈。"
    "按 JSON 数组返回,每条建议结构必须严格符合给出的 schema。"
)


def generate_suggestions(
    resume: ResumeData,
    job: JobRequirement,
    report: MatchReport,
    llm: LLMClient,
) -> List[ResumeSuggestion]:
    """调用 LLM 生成建议,并对结果做 schema 校验和排序."""

    evidence = _build_evidence(resume, job, report)
    user_prompt = (
        "请基于下面的证据,生成 5-10 条简历修改建议。\n\n"
        f"## 简历摘要\n{_resume_digest(resume)}\n\n"
        f"## 岗位摘要\n{_job_digest(job)}\n\n"
        f"## 匹配证据\n{evidence}\n\n"
        "每条建议的 JSON 字段:\n"
        "type: content|structure|keyword|quantify|format\n"
        "priority: high|medium|low\n"
        "section: summary|skills|work_experience|project|education|certification|overall\n"
        "current: 当前简历中的原文片段(若无可省略)\n"
        "suggestion: 具体修改建议(必须可执行)\n"
        "example: 修改后示例\n"
        "reason: 给出该建议的依据,引用上面的证据\n"
        "related_jd_requirement: 关联的岗位要求描述\n\n"
        "只输出 JSON 数组,不要任何额外文字。"
    )

    raw = llm.chat_text(system=_SYSTEM_PROMPT, user=user_prompt)
    payload = _extract_json_array(raw)
    payload = _normalize_suggestions(payload)
    suggestions = _SUGGESTION_ADAPTER.validate_python(payload)
    return _sort_suggestions(suggestions)


def _build_evidence(resume: ResumeData, job: JobRequirement, report: MatchReport) -> str:
    skill_evidence = {
        "matched": [s.skill for s in report.skill_gap.matched],
        "missing_must": [
            s.skill
            for s in report.skill_gap.missing
        ],
        "partial": [s.skill for s in report.skill_gap.partial],
        "coverage": report.skill_gap.coverage,
    }
    return json.dumps(
        {
            "skill_evidence": skill_evidence,
            "experience": {
                "years_required": report.experience.years_required,
                "years_estimated": report.experience.years_estimated,
                "notes": report.experience.notes,
            },
            "keywords": {
                "matched": report.keywords.matched,
                "missing": report.keywords.missing,
                "coverage": report.keywords.coverage,
            },
            "hard_requirements_gaps": report.hard_requirements_gaps,
            "overall_score": report.overall_score,
        },
        ensure_ascii=False,
    )


def _resume_digest(resume: ResumeData) -> str:
    return json.dumps(
        {
            "name": resume.name,
            "summary": resume.summary,
            "skills": resume.skills,
            "work": [
                {
                    "company": w.company,
                    "position": w.position,
                    "description": (w.description or "")[:200],
                    "achievements": w.achievements,
                }
                for w in (resume.work_experience or [])
            ],
            "projects": [
                {
                    "name": p.name,
                    "role": p.role,
                    "description": (p.description or "")[:200],
                    "technologies": p.technologies,
                }
                for p in (resume.projects or [])
            ],
        },
        ensure_ascii=False,
    )


def _job_digest(job: JobRequirement) -> str:
    return json.dumps(
        {
            "position": job.position,
            "company": job.company,
            "responsibilities": job.responsibilities,
            "hard_skills": [r.description for r in job.hard_skills],
            "soft_skills": [r.description for r in job.soft_skills],
            "experience": [r.description for r in job.experience],
            "education": [r.description for r in job.education],
            "keywords": job.keywords,
        },
        ensure_ascii=False,
    )


def _extract_json_array(text: str) -> list:
    """从 LLM 返回中抽出 JSON 数组."""
    import re

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("LLM 输出未包含 JSON 数组")
    return json.loads(match.group(0))


def _coerce_str(value):
    """将可能的 list/dict 安全归一化为字符串."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value if v is not None)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _normalize_suggestions(items: list) -> list:
    """LLM 偶尔会把字符串字段输出成列表/对象,或输出不在枚举内的值,这里做一次规整."""
    # 合法枚举值映射(LLM 可能输出 skill/experience 等不在枚举内的值)
    _type_map = {
        "skill": "content", "skills": "content", "experience": "content",
        "education": "content", "certification": "content",
    }
    _priority_map = {
        "critical": "high", "important": "high", "normal": "medium", "low": "low",
    }
    _section_map = {
        "skill": "skills", "work": "work_experience", "exp": "work_experience",
        "project": "project", "edu": "education", "cert": "certification",
        "overall": "overall", "summary": "summary",
    }
    for it in items:
        if not isinstance(it, dict):
            continue
        for k in ("current", "example", "suggestion", "reason", "related_jd_requirement"):
            if k in it:
                it[k] = _coerce_str(it[k])
        # 修正非法枚举值
        if "type" in it and isinstance(it["type"], str):
            it["type"] = _type_map.get(it["type"].lower(), it["type"])
        if "priority" in it and isinstance(it["priority"], str):
            it["priority"] = _priority_map.get(it["priority"].lower(), it["priority"])
        if "section" in it and isinstance(it["section"], str):
            it["section"] = _section_map.get(it["section"].lower(), it["section"])
    return items


def _sort_suggestions(items: List[ResumeSuggestion]) -> List[ResumeSuggestion]:
    priority_rank = {
        SuggestionPriority.HIGH: 0,
        SuggestionPriority.MEDIUM: 1,
        SuggestionPriority.LOW: 2,
    }
    return sorted(items, key=lambda s: (priority_rank.get(s.priority, 99), s.section.value))
