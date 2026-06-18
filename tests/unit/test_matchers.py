"""匹配器单元测试(纯规则,无 LLM 依赖).

- experience_matcher: 年限估算 + 评分
- keyword_matcher: 关键词包含匹配
- skill_matcher 字面回退路径
"""
from __future__ import annotations

from tests.runner import unit
from app.models.job_requirement import JobRequirement, Requirement, Priority, RequirementCategory
from app.models.resume import ResumeData, WorkExperience
from app.matchers.experience_matcher import analyze_experience, _estimate_years, _parse_year_month
from app.matchers.keyword_matcher import analyze_keywords
from app.matchers.skill_matcher import analyze_skill_gap


def _resume_with_experience(spans: list[tuple[str, str, str, str]]) -> ResumeData:
    """构造带工作经历的简历. spans: (公司, 岗位, start, end)."""
    return ResumeData(
        name="Test User",
        work_experience=[
            WorkExperience(
                company=company,
                position=position,
                start_date=start,
                end_date=end,
            )
            for company, position, start, end in spans
        ],
    )


@unit
def test_parse_year_month_full():
    assert _parse_year_month("2022.03") == (2022, 3)
    assert _parse_year_month("2020-07") == (2020, 7)
    assert _parse_year_month("2021年5月") == (2021, 5)


@unit
def test_parse_year_month_year_only():
    assert _parse_year_month("2019") == (2019, None)
    assert _parse_year_month("garbage") == (None, None)


@unit
def test_estimate_years_simple():
    """2018.1 - 2022.1 估算 4 年."""
    r = _resume_with_experience([
        ("CoA", "Dev", "2018.01", "2022.01"),
    ])
    years = _estimate_years(r)
    assert years is not None
    assert 3.5 <= years <= 4.5, f"实际 {years}"


@unit
def test_estimate_years_overlapping():
    """多个工作段累加."""
    r = _resume_with_experience([
        ("CoA", "Dev", "2018.01", "2020.06"),
        ("CoB", "Senior", "2020.07", "2024.12"),
    ])
    years = _estimate_years(r)
    assert years is not None
    assert 6.0 <= years <= 7.5, f"实际 {years}"


@unit
def test_estimate_years_empty():
    """无工作经历时返回 None."""
    r = ResumeData()
    assert _estimate_years(r) is None


@unit
def test_experience_match_meets_requirement():
    """年限满足要求时,评分应当 >= 0.9."""
    resume = _resume_with_experience([
        ("CoA", "后端工程师", "2019.01", "2024.01"),
    ])
    job = JobRequirement(
        experience=[Requirement(description="3 年以上后端经验", category=RequirementCategory.EXPERIENCE)],
    )
    result = analyze_experience(resume, job)
    assert result.years_required == 3
    assert result.years_estimated is not None
    assert result.years_estimated >= 4
    assert result.score >= 0.9
    assert not result.notes, f"不应有 notes,实际 {result.notes}"


@unit
def test_experience_match_below_requirement():
    """年限不足时,评分下降且加 note."""
    resume = _resume_with_experience([
        ("CoA", "开发", "2023.06", "2024.06"),
    ])
    job = JobRequirement(
        experience=[Requirement(description="5 年以上开发经验", category=RequirementCategory.EXPERIENCE)],
    )
    result = analyze_experience(resume, job)
    assert result.years_required == 5
    assert result.score < 0.9
    assert result.notes
    assert "经验年限不足" in result.notes[0]


@unit
def test_experience_match_no_requirement():
    """无年限要求时,默认评分 0.7."""
    resume = _resume_with_experience([("CoA", "开发", "2020.01", "2024.01")])
    job = JobRequirement()  # 无 experience
    result = analyze_experience(resume, job)
    assert result.years_required is None
    assert result.score == 0.7


@unit
def test_keyword_match_all_present():
    """关键词全命中."""
    resume = ResumeData(
        skills=["Python", "FastAPI"],
        summary="熟练使用 Kafka 和 Redis",
    )
    job = JobRequirement(keywords=["Python", "FastAPI", "Kafka"])
    result = analyze_keywords(resume, job)
    assert set(result.matched) == {"Python", "FastAPI", "Kafka"}
    assert result.missing == []
    assert result.coverage == 1.0


@unit
def test_keyword_match_partial():
    """部分命中."""
    resume = ResumeData(skills=["Python"])
    job = JobRequirement(keywords=["Python", "Rust", "Go"])
    result = analyze_keywords(resume, job)
    assert result.matched == ["Python"]
    assert set(result.missing) == {"Rust", "Go"}
    assert abs(result.coverage - 1/3) < 0.01


@unit
def test_keyword_match_empty_job_keywords():
    """岗位无关键词时,默认 coverage = 1.0."""
    resume = ResumeData(skills=["Python"])
    job = JobRequirement()
    result = analyze_keywords(resume, job)
    assert result.coverage == 1.0
    assert result.matched == []
    assert result.missing == []


@unit
def test_skill_literal_match_basic():
    """字面匹配:Python 直接命中,Redis 不存在则 missing."""
    resume = ResumeData(
        skills=["Python", "FastAPI"],
        summary="高并发后端开发",
        projects=[],
    )
    job = JobRequirement(
        hard_skills=[Requirement(description="Python"), Requirement(description="Redis")],
        soft_skills=[],
    )
    result = analyze_skill_gap(resume, job, force_literal=True)
    matched_skills = [s.skill for s in result.matched]
    missing_skills = [s.skill for s in result.missing]
    assert "Python" in matched_skills
    assert "Redis" in missing_skills
    assert result.coverage == 0.5


@unit
def test_skill_literal_partial_match():
    """字面部分匹配:长 token 前缀部分命中."""
    resume = ResumeData(skills=["PostgreSQL"])
    job = JobRequirement(
        hard_skills=[Requirement(description="PostgreSQL 数据库")],
    )
    result = analyze_skill_gap(resume, job, force_literal=True)
    # "PostgreSQL" 在描述中出现,视为 matched(因为 alias 拆分后 "PostgreSQL" 也在)
    assert any(s.matched for s in result.matched + result.partial)


@unit
def test_skill_no_requirement():
    """无技能要求时,matched/missing/partial 均为空,coverage 由 0/total 决定."""
    resume = ResumeData(skills=["Python"])
    job = JobRequirement()
    result = analyze_skill_gap(resume, job, force_literal=True)
    # 实际实现:total = 0 时,coverage = 0.0(分母为 0 时分子也为 0)
    assert result.matched == []
    assert result.missing == []
    assert result.partial == []
    assert result.coverage == 0.0