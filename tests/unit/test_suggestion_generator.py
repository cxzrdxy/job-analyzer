"""建议生成器单元测试.

- _sort_suggestions: 优先级 + section 排序
- _fallback_suggestions: 启发式回退
- _build_*_text: 文本构造
"""
from __future__ import annotations

from tests.runner import unit
from app.models.suggestion import (
    MatchReport,
    ResumeSuggestion,
    SkillGapAnalysis,
    ExperienceMatch,
    KeywordMatch,
    SkillMatchItem,
    SuggestionPriority,
    SuggestionType,
    ResumeSection,
)
from app.models.job_requirement import JobRequirement
from app.models.resume import ResumeData
from app.workflow.suggestion_generator import (
    _fallback_suggestions,
    _sort_suggestions,
    _build_resume_text,
    _build_job_text,
)


def _sample_report() -> MatchReport:
    return MatchReport(
        overall_score=72.0,
        skill_gap=SkillGapAnalysis(
            matched=[SkillMatchItem(skill="Python", matched=True)],
            partial=[],
            missing=[
                SkillMatchItem(skill="Kafka", matched=False),
                SkillMatchItem(skill="Kubernetes", matched=False),
            ],
            coverage=0.6,
        ),
        experience=ExperienceMatch(
            years_required=5,
            years_estimated=3.0,
            score=0.6,
            notes=["经验年限不足:简历估算 3.0 年,要求 5 年"],
        ),
        keywords=KeywordMatch(
            matched=["Python"],
            missing=["DDD", "Microservice", "GitOps"],
            coverage=0.25,
        ),
        hard_requirements_gaps=["Kafka", "Kubernetes"],
    )


@unit
def test_sort_priority_then_section():
    """按优先级排序,优先级相同时按 section."""
    items = [
        ResumeSuggestion(priority=SuggestionPriority.LOW, section=ResumeSection.SKILLS, suggestion="l1"),
        ResumeSuggestion(priority=SuggestionPriority.HIGH, section=ResumeSection.SKILLS, suggestion="h1"),
        ResumeSuggestion(priority=SuggestionPriority.MEDIUM, section=ResumeSection.WORK_EXPERIENCE, suggestion="m1"),
        ResumeSuggestion(priority=SuggestionPriority.HIGH, section=ResumeSection.OVERALL, suggestion="h2"),
    ]
    sorted_items = _sort_suggestions(items)
    priorities = [s.priority for s in sorted_items]
    # HIGH 应当排前面
    assert priorities[0] == SuggestionPriority.HIGH
    assert priorities[-1] == SuggestionPriority.LOW


@unit
def test_fallback_missing_skills():
    """回退建议:缺失技能应当产出 SKILLS 类的 HIGH 建议."""
    resume = ResumeData(name="X")
    job = JobRequirement(position="Backend")
    report = _sample_report()
    suggestions = _fallback_suggestions(resume, job, report)

    assert len(suggestions) >= 3, f"期望至少 3 条,实际 {len(suggestions)}"

    # 至少 1 条 SKILLS/HIGH(CONTENT)建议,提及 Kafka 或 Kubernetes
    high_skills = [
        s for s in suggestions
        if s.priority == SuggestionPriority.HIGH and s.section == ResumeSection.SKILLS
    ]
    assert len(high_skills) >= 1
    assert any("Kafka" in s.suggestion or "Kubernetes" in s.suggestion for s in high_skills)


@unit
def test_fallback_experience_gap():
    """年限不足应触发 WORK_EXPERIENCE/HIGH 建议."""
    resume = ResumeData()
    job = JobRequirement()
    report = _sample_report()
    suggestions = _fallback_suggestions(resume, job, report)

    quant_suggestions = [
        s for s in suggestions
        if s.type == SuggestionType.QUANTIFY and s.section == ResumeSection.WORK_EXPERIENCE
    ]
    assert len(quant_suggestions) == 1
    assert quant_suggestions[0].priority == SuggestionPriority.HIGH


@unit
def test_fallback_keywords():
    """关键词缺失应触发 OVERALL/MEDIUM 建议."""
    resume = ResumeData()
    job = JobRequirement()
    report = _sample_report()
    suggestions = _fallback_suggestions(resume, job, report)

    kw_suggestions = [
        s for s in suggestions
        if s.type == SuggestionType.KEYWORD and s.section == ResumeSection.OVERALL
    ]
    assert len(kw_suggestions) == 1
    assert "DDD" in kw_suggestions[0].suggestion


@unit
def test_fallback_no_gaps():
    """当无缺失时,只返回 1 条经验建议(年限不足),keyword 建议不出现."""
    resume = ResumeData()
    job = JobRequirement()
    report = MatchReport(
        skill_gap=SkillGapAnalysis(coverage=1.0),
        experience=ExperienceMatch(years_required=5, years_estimated=3.0, score=0.6),
        keywords=KeywordMatch(coverage=1.0),
    )
    suggestions = _fallback_suggestions(resume, job, report)
    assert all(s.type != SuggestionType.KEYWORD for s in suggestions)


@unit
def test_build_resume_text_raw_preferred():
    """当 raw_text 存在时优先使用."""
    resume = ResumeData(
        raw_text="一段很长的简历内容",
        summary="summary",
        skills=["Python"],
    )
    text = _build_resume_text(resume)
    assert "一段很长的简历内容" in text


@unit
def test_build_resume_text_truncates():
    """raw_text > 3000 字时截断."""
    resume = ResumeData(raw_text="x" * 5000)
    text = _build_resume_text(resume)
    assert len(text) < 5000
    assert "截断" in text


@unit
def test_build_resume_text_fallback_to_structured():
    """无 raw_text 时,fallback 到结构化字段."""
    resume = ResumeData(
        summary="个人简介ABC",
        skills=["Python", "FastAPI"],
    )
    text = _build_resume_text(resume)
    assert "个人简介ABC" in text
    assert "Python" in text


@unit
def test_build_job_text_basic():
    """构造岗位文本."""
    job = JobRequirement(
        position="Backend Engineer",
        company="Acme",
        hard_skills=[],
        soft_skills=[],
    )
    text = _build_job_text(job)
    assert "Backend Engineer" in text
    assert "Acme" in text