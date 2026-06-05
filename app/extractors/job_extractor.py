"""岗位 JD 结构化抽取."""
from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.job_requirement import JobRequirement

logger = get_logger(__name__)


_JOB_SYSTEM = (
    "你是一名资深招聘分析师,擅长把岗位 JD 拆解为结构化需求。"
    "请严格按 JSON Schema 输出,优先区分 must_have 与 nice_to_have。"
)

_JOB_SCHEMA_HINT = """
期望 JSON 结构:
{
  "position": "string",
  "company": "string|null",
  "department": "string|null",
  "salary_range": "string|null",
  "location": "string|null",
  "hard_skills": [{"category": "skill|experience|education|certification|other",
                   "description": "string", "priority": "must_have|nice_to_have",
                   "evidence": "string|null"}],
  "soft_skills": [同 hard_skills],
  "experience": [同 hard_skills],
  "education": [同 hard_skills],
  "responsibilities": ["string"],
  "keywords": ["string"]
}
""".strip()


class JobExtractor:
    """调用 LLM 把 JD 文本转为 JobRequirement."""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    def extract(self, text: str) -> JobRequirement:
        if not text or not text.strip():
            return JobRequirement(raw_text="", confidence=0.0, warnings=["empty_text"])

        truncated = _truncate(text, max_chars=8000)
        user_prompt = (
            f"请从以下岗位 JD 中提取结构化要求。\n\n"
            f"{_JOB_SCHEMA_HINT}\n\n"
            f"JD 原文:\n{truncated}"
        )
        parsed = self.llm.chat_json(
            system=_JOB_SYSTEM,
            user=user_prompt,
            schema=JobRequirement,
        )
        parsed.raw_text = text
        return parsed


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 200] + "\n...[truncated]"
