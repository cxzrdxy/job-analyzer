"""简历修改建议与匹配分析模型."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SuggestionType(str, Enum):
    CONTENT = "content"
    STRUCTURE = "structure"
    KEYWORD = "keyword"
    QUANTIFY = "quantify"
    FORMAT = "format"


class SuggestionPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResumeSection(str, Enum):
    SUMMARY = "summary"
    SKILLS = "skills"
    WORK_EXPERIENCE = "work_experience"
    PROJECT = "project"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    OVERALL = "overall"


class ResumeSuggestion(BaseModel):
    """单条简历修改建议."""

    type: SuggestionType
    priority: SuggestionPriority
    section: ResumeSection
    current: Optional[str] = None
    suggestion: str
    example: Optional[str] = None
    reason: str
    related_jd_requirement: Optional[str] = None


class SkillMatchItem(BaseModel):
    skill: str
    matched: bool
    confidence: float = 1.0
    evidence: Optional[str] = None  # 简历中命中的原文片段


class SkillGapAnalysis(BaseModel):
    matched: List[SkillMatchItem] = Field(default_factory=list)
    missing: List[SkillMatchItem] = Field(default_factory=list)
    partial: List[SkillMatchItem] = Field(default_factory=list)
    coverage: float = 0.0  # 0-1,综合覆盖率


class ExperienceMatch(BaseModel):
    years_required: Optional[float] = None
    years_estimated: Optional[float] = None
    matched_industries: List[str] = Field(default_factory=list)
    related_roles: List[str] = Field(default_factory=list)
    score: float = 0.0
    notes: List[str] = Field(default_factory=list)


class KeywordMatch(BaseModel):
    matched: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    coverage: float = 0.0


class MatchReport(BaseModel):
    """综合匹配结果."""

    overall_score: float = 0.0  # 0-100
    skill_gap: SkillGapAnalysis = Field(default_factory=SkillGapAnalysis)
    experience: ExperienceMatch = Field(default_factory=ExperienceMatch)
    keywords: KeywordMatch = Field(default_factory=KeywordMatch)
    hard_requirements_gaps: List[str] = Field(default_factory=list)
