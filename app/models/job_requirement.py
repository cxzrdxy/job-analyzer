"""岗位需求相关数据模型."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Priority(str, Enum):
    """要求优先级."""

    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class RequirementCategory(str, Enum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    OTHER = "other"


class Requirement(BaseModel):
    category: RequirementCategory = RequirementCategory.OTHER
    description: str
    priority: Priority = Priority.MUST_HAVE
    evidence: Optional[str] = None  # JD 原文片段,便于溯源


class JobRequirement(BaseModel):
    position: str = ""
    company: Optional[str] = None
    department: Optional[str] = None
    salary_range: Optional[str] = None
    location: Optional[str] = None

    hard_skills: List[Requirement] = Field(default_factory=list)
    soft_skills: List[Requirement] = Field(default_factory=list)
    experience: List[Requirement] = Field(default_factory=list)
    education: List[Requirement] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    raw_text: str = ""
    confidence: float = 1.0
    warnings: List[str] = Field(default_factory=list)
