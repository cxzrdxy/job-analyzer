"""简历结构化抽取."""
from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.resume import ResumeData

logger = get_logger(__name__)


_RESUME_SYSTEM = (
    "你是一名资深招聘助理,擅长从简历文本中提取结构化信息。"
    "请严格按 JSON Schema 输出,不要输出任何额外文字、解释或 Markdown。"
)

_RESUME_SCHEMA_HINT = """
期望 JSON 结构(字段名严格保持,缺失字段填空字符串或空数组):
{
  "name": "string",
  "contact": {"phone": "string", "email": "string", "location": "string", "links": ["string"]},
  "summary": "string",
  "skills": ["string"],
  "education": [{"school": "string", "degree": "string", "major": "string",
                 "start_date": "string", "end_date": "string", "description": "string"}],
  "work_experience": [{"company": "string", "position": "string",
                       "start_date": "string", "end_date": "string",
                       "description": "string", "achievements": ["string"]}],
  "projects": [{"name": "string", "role": "string", "start_date": "string",
                "end_date": "string", "description": "string", "technologies": ["string"]}],
  "certifications": [{"name": "string", "issuer": "string", "date": "string"}]
}
""".strip()


class ResumeExtractor:
    """调用 LLM 把简历文本转为 ResumeData."""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    def extract(self, text: str) -> ResumeData:
        if not text or not text.strip():
            return ResumeData(raw_text="", confidence=0.0, warnings=["empty_text"])

        truncated = _truncate(text, max_chars=12000)
        user_prompt = (
            f"请从以下简历中提取信息。\n\n"
            f"{_RESUME_SCHEMA_HINT}\n\n"
            f"简历原文:\n{truncated}"
        )
        parsed = self.llm.chat_json(
            system=_RESUME_SYSTEM,
            user=user_prompt,
            schema=ResumeData,
        )
        parsed.raw_text = text
        return parsed


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 200] + "\n...[truncated]"
