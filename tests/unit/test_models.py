"""模型单元测试.

- ResumeData / JobRequirement / MatchReport 数据模型校验
- Enum 值约束
- 默认值
"""
from __future__ import annotations

from tests.runner import unit
from app.models.resume import ResumeData, WorkExperience, Education, ProjectExperience
from app.models.job_requirement import (
    JobRequirement, Requirement, Priority, RequirementCategory,
)
from app.models.suggestion import (
    MatchReport, SkillGapAnalysis, ExperienceMatch, KeywordMatch,
    ResumeSuggestion, SuggestionType, SuggestionPriority, ResumeSection,
)


@unit
def test_resume_defaults():
    """空 ResumeData 应当具有合理默认值."""
    r = ResumeData()
    assert r.name is None
    assert r.contact.phone is None
    assert r.skills == []
    assert r.work_experience == []
    assert r.projects == []
    assert r.raw_text == ""
    assert r.confidence == 1.0


@unit
def test_work_experience_required_company():
    """WorkExperience.company 是必填."""
    from pydantic import ValidationError

    try:
        WorkExperience()
    except ValidationError:
        return
    raise AssertionError("company 必填但未抛异常")


@unit
def test_job_requirement_defaults():
    """JobRequirement 默认空集合."""
    job = JobRequirement()
    assert job.position == ""
    assert job.company is None
    assert job.hard_skills == []
    assert job.soft_skills == []
    assert job.experience == []
    assert job.keywords == []


@unit
def test_requirement_category_enum():
    """Requirement category 必须属于枚举."""
    r = Requirement(category=RequirementCategory.SKILL, description="Python")
    assert r.priority == Priority.MUST_HAVE


@unit
def test_suggestion_section_enum_values():
    """section 枚举值应当正确."""
    assert ResumeSection.SKILLS.value == "skills"
    assert ResumeSection.WORK_EXPERIENCE.value == "work_experience"
    assert ResumeSection.PROJECT.value == "project"


@unit
def test_match_report_defaults():
    """MatchReport 默认值."""
    report = MatchReport()
    assert report.overall_score == 0.0
    assert report.skill_gap.coverage == 0.0
    assert report.experience.score == 0.0
    assert report.keywords.coverage == 0.0
    assert report.hard_requirements_gaps == []


@unit
def test_suggestion_model_dump_round_trip():
    """ResumeSuggestion dump/load 应当无损."""
    s = ResumeSuggestion(
        type=SuggestionType.QUANTIFY,
        priority=SuggestionPriority.HIGH,
        section=ResumeSection.WORK_EXPERIENCE,
        current="原文本",
        suggestion="改写建议",
        example="示例文本",
        reason="理由",
        related_jd_requirement="JD 要求",
    )
    d = s.model_dump()
    s2 = ResumeSuggestion(**d)
    assert s2.suggestion == "改写建议"
    assert s2.section == ResumeSection.WORK_EXPERIENCE
    assert s2.related_jd_requirement == "JD 要求"


@unit
def test_skill_gap_coverage_range():
    """coverage 应当是 0-1."""
    sg = SkillGapAnalysis(coverage=0.75)
    assert sg.coverage == 0.75

    # 边界值
    sg2 = SkillGapAnalysis(coverage=0.0)
    sg3 = SkillGapAnalysis(coverage=1.0)
    assert sg2.coverage == 0.0
    assert sg3.coverage == 1.0


@unit
def test_resume_project_experience():
    """ProjectExperience 模型可用."""
    p = ProjectExperience(
        name="求职分析智能体",
        role="开发者",
        description="LangGraph 工作流",
        technologies=["Python", "FastAPI"],
    )
    assert p.name == "求职分析智能体"
    assert "FastAPI" in p.technologies


@unit
def test_education_model():
    """Education 模型."""
    e = Education(school="清华大学", degree="硕士", major="计算机")
    d = e.model_dump()
    assert d["school"] == "清华大学"