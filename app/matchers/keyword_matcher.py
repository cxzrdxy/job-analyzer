"""关键词匹配."""
from __future__ import annotations

import re
from typing import List

from app.core.logging import get_logger
from app.models.job_requirement import JobRequirement
from app.models.resume import ResumeData
from app.models.suggestion import KeywordMatch

logger = get_logger(__name__)


def analyze_keywords(resume: ResumeData, job: JobRequirement) -> KeywordMatch:
    keywords: List[str] = list(job.keywords or [])
    if not keywords:
        return KeywordMatch(matched=[], missing=[], coverage=1.0)

    corpus = _resume_corpus(resume).lower()
    matched: list[str] = []
    missing: list[str] = []
    for kw in keywords:
        token = re.sub(r"\s+", " ", kw.strip().lower())
        if token and token in corpus:
            matched.append(kw)
        else:
            missing.append(kw)

    coverage = round(len(matched) / max(1, len(keywords)), 3)
    return KeywordMatch(matched=matched, missing=missing, coverage=coverage)


def _resume_corpus(resume: ResumeData) -> str:
    parts: list[str] = [resume.summary or "", ",".join(resume.skills or [])]
    for item in resume.work_experience or []:
        parts.append(item.description or "")
        parts.extend(item.achievements or [])
    for item in resume.projects or []:
        parts.append(item.description or "")
    return "\n".join(parts)
