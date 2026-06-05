"""经验匹配."""
from __future__ import annotations

import re
from typing import List, Optional

from app.core.logging import get_logger
from app.models.job_requirement import JobRequirement, Requirement
from app.models.resume import ResumeData
from app.models.suggestion import ExperienceMatch

logger = get_logger(__name__)

_YEAR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:年|years?)", re.IGNORECASE)


def _estimate_years(resume: ResumeData) -> Optional[float]:
    total_months = 0
    for item in resume.work_experience or []:
        start = item.start_date or ""
        end = item.end_date or ""
        months = _span_to_months(start, end)
        if months:
            total_months += months
    if total_months <= 0:
        return None
    return round(total_months / 12, 1)


def _span_to_months(start: str, end: str) -> int:
    if not start:
        return 0
    s_year, s_month = _parse_year_month(start)
    e_year, e_month = _parse_year_month(end or "至今")
    if s_year is None:
        return 0
    if e_year is None:
        return 0
    sm = s_month or 1
    em = e_month or 12
    return max(0, (e_year - s_year) * 12 + (em - sm) + 1)


def _parse_year_month(text: str) -> tuple[Optional[int], Optional[int]]:
    match = re.search(r"(\d{4})[.\-/年](\d{1,2})?", text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2)) if match.group(2) else None
        return year, month
    match = re.search(r"(\d{4})", text)
    if match:
        return int(match.group(1)), None
    return None, None


def _required_years(job: JobRequirement) -> Optional[float]:
    for req in job.experience or []:
        match = _YEAR_RE.search(req.description or "")
        if match:
            return float(match.group(1))
    return None


def analyze_experience(resume: ResumeData, job: JobRequirement) -> ExperienceMatch:
    years_required = _required_years(job)
    years_estimated = _estimate_years(resume)

    industries = [req.description for req in job.experience or [] if req.description]
    related_roles = [
        (item.position or "")
        for item in resume.work_experience or []
        if item.position and any(_loose_match(item.position, ind) for ind in industries)
    ]

    notes: list[str] = []
    score = 0.6
    if years_required is not None and years_estimated is not None:
        ratio = min(1.0, years_estimated / max(1.0, years_required))
        score = round(0.5 + 0.5 * ratio, 3)
        if years_estimated < years_required:
            notes.append(f"经验年限不足:简历估算 {years_estimated} 年,要求 {years_required} 年")
    elif years_required is None:
        score = 0.7

    return ExperienceMatch(
        years_required=years_required,
        years_estimated=years_estimated,
        related_roles=related_roles,
        score=score,
        notes=notes,
    )


def _loose_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a.lower() in b.lower() or b.lower() in a.lower()
