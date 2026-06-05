"""简历相关数据模型."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    """联系方式,避免使用裸 dict."""

    phone: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    links: List[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str
    degree: Optional[str] = None
    major: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class WorkExperience(BaseModel):
    company: str
    position: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)


class ProjectExperience(BaseModel):
    name: str
    role: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None


class ResumeData(BaseModel):
    """简历结构化结果."""

    name: Optional[str] = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    projects: List[ProjectExperience] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    raw_text: str = ""
    confidence: float = 1.0
    warnings: List[str] = Field(default_factory=list)
