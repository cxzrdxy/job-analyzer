"""技能差距分析.

支持两种匹配策略:

- **语义匹配(默认)**:调用一次 LLM,一次性判断每条硬/软技能的状态。
  理解等价物(如 PgVector ≡ Milvus / Qdrant)、隐含使用(用 LangGraph
  必然用过 LLM API)与程度差异(了解 vs 精通)。LLM 失败时自动回退。
- **字面匹配(回退 / 调试)**:纯字符串包含匹配,速度快但易误判。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal

from app.core.errors import ExtractError
from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.job_requirement import JobRequirement, Requirement
from app.models.resume import ResumeData
from app.models.suggestion import SkillGapAnalysis, SkillMatchItem

logger = get_logger(__name__)


# ============================================================================
# 语义匹配 (LLM)
# ============================================================================

_SEMANTIC_SYSTEM = (
    "你是一名资深求职教练,擅长在简历与岗位要求之间做语义级匹配。"
    "理解等价物(如 PgVector ≡ Milvus / Qdrant)、隐含使用(如 用 LangGraph "
    "必然用过某种 LLM API)与程度差异(了解 vs 精通)。"
    "请严格按 JSON Schema 输出,不要追加任何解释文字或 Markdown 包装。"
)

_SEMANTIC_USER_TEMPLATE = """请阅读下方候选人简历与岗位要求,逐条判断每项【硬技能】/【软技能】是否被简历覆盖。

【判断规则】
- matched:简历中明确体现该要求(直接出现或语义等价)
- partial:简历中部分相关,但深度/年限/经验不足,或仅处于"了解"阶段
- missing:简历完全未涉及该要求

【等价物参考(仅供判断,不要硬套)】
- 向量数据库 ≈ Milvus / Qdrant / PgVector / Chroma / Weaviate / FAISS
- Python 异步框架 ≈ FastAPI(asyncio) / aiohttp / Sanic / Tornado
- Python ORM ≈ SQLAlchemy / SQLModel / Tortoise ORM / Django ORM
- 消息队列 ≈ Kafka / RabbitMQ / RocketMQ(Celery broker 偏弱,通常判 partial)
- LLM API ≈ OpenAI / DeepSeek / 通义千问 / 智谱 / 月之暗面 / Claude / Gemini
- 求职/招聘类 SaaS 视为智能简历/求职产品等同类经验

【特别提醒】
1. 括号内的示例不构成硬要求。例如"LLM (OpenAI / DeepSeek / 通义千问) 等至少一种"
   只要简历里用了 LangGraph/LangChain 就能算 matched。
2. 隐含使用可算 matched。例如:用 LangGraph → 必然用过某种 LLM API。
3. evidence 字段请引用简历原文片段(30 字以内),不要捏造。
4. 输出的硬/软技能数组必须与下方输入列表顺序与数量完全一致,skill 字段原句照抄。

## 简历原文
{resume_text}

## 硬技能列表({hard_n} 条)
{hard_block}

## 软技能列表({soft_n} 条)
{soft_block}

请严格输出 JSON,字段:
{{
  "hard_skills": [{{"skill": "原句照抄", "status": "matched|partial|missing", "evidence": "..."}}],
  "soft_skills": [同上结构],
  "coverage": 0.0~1.0,
  "notes": "1-2 句整体观察"
}}
"""


class _SkillEntry(BaseModel):
    skill: str
    status: Literal["matched", "partial", "missing"]
    evidence: str = ""


class _SkillGapSchema(BaseModel):
    hard_skills: List[_SkillEntry]
    soft_skills: List[_SkillEntry]
    coverage: float = Field(ge=0.0, le=1.0)
    notes: str = ""


def _format_requirements(reqs: Iterable[Requirement]) -> str:
    return "\n".join(f"  {i+1}. {r.description}" for i, r in enumerate(reqs)) or "  (无)"


def _normalize(s: str) -> str:
    return re.sub(r"[\s/(),]+", "", s).lower()


def _find_entry(skill: str, lookups: Dict[str, _SkillEntry]) -> Optional[_SkillEntry]:
    """精确 → 归一化 → 短文本包含 的三级容错查找。"""
    if skill in lookups:
        return lookups[skill]
    norm = _normalize(skill)
    for k, v in lookups.items():
        if _normalize(k) == norm:
            return v
    for k, v in lookups.items():
        nk = _normalize(k)
        if len(nk) >= 4 and nk in norm:
            return v
    return None


def _classify_entry(
    skill: str,
    entry: Optional[_SkillEntry],
    matched: List[SkillMatchItem],
    partial: List[SkillMatchItem],
    missing: List[SkillMatchItem],
) -> None:
    evidence = (entry.evidence if entry and entry.evidence else None)
    if entry is None or entry.status == "missing":
        missing.append(SkillMatchItem(skill=skill, matched=False, evidence=evidence))
    elif entry.status == "matched":
        matched.append(SkillMatchItem(skill=skill, matched=True, evidence=evidence))
    elif entry.status == "partial":
        partial.append(SkillMatchItem(skill=skill, matched=False, confidence=0.5, evidence=evidence))
    else:
        missing.append(SkillMatchItem(skill=skill, matched=False, evidence=evidence))


def _semantic_skill_gap(
    resume: ResumeData,
    job: JobRequirement,
    llm_client: LLMClient,
) -> SkillGap:
    """调用 LLM 一次性判断所有硬/软技能。"""
    resume_text = (resume.raw_text or "")[:10000]
    user_prompt = _SEMANTIC_USER_TEMPLATE.format(
        resume_text=resume_text,
        hard_n=len(job.hard_skills),
        soft_n=len(job.soft_skills),
        hard_block=_format_requirements(job.hard_skills),
        soft_block=_format_requirements(job.soft_skills),
    )

    result = llm_client.chat_json(
        system=_SEMANTIC_SYSTEM,
        user=user_prompt,
        schema=_SkillGapSchema,
        max_retries=1,
    )

    hard_lookups: Dict[str, _SkillEntry] = {e.skill: e for e in result.hard_skills}
    soft_lookups: Dict[str, _SkillEntry] = {e.skill: e for e in result.soft_skills}

    matched: List[SkillMatchItem] = []
    partial: List[SkillMatchItem] = []
    missing: List[SkillMatchItem] = []

    for req in job.hard_skills:
        _classify_entry(req.description, _find_entry(req.description, hard_lookups), matched, partial, missing)
    for req in job.soft_skills:
        _classify_entry(req.description, _find_entry(req.description, soft_lookups), matched, partial, missing)

    return SkillGapAnalysis(
        matched=matched,
        partial=partial,
        missing=missing,
        coverage=round(float(result.coverage), 4),
    )


# ============================================================================
# 字面匹配(回退 / 调试)
# ============================================================================

def _build_corpus(resume: ResumeData) -> str:
    pieces: List[str] = []
    pieces.extend(s.lower() for s in resume.skills)
    pieces.extend(e.description.lower() for e in resume.work_experience)
    pieces.extend(p.description.lower() for p in resume.projects)
    for p in resume.projects:
        pieces.extend(t.lower() for t in p.technologies)
    return "\n".join(pieces)


def _alias_keys(text: str) -> List[str]:
    base = text.strip().lower()
    no_paren = re.sub(r"[（(][^）)]*[）)]", "", base).strip()
    keys = {base, no_paren}
    keys.update(part.strip() for part in base.replace(" ", "/").split("/") if part.strip())
    return [k for k in keys if k]


def _partial_hit(key: str, corpus: str) -> bool:
    if len(key) < 4:
        return False
    return key[: max(3, len(key) - 2)] in corpus


def _literal_skill_gap(resume: ResumeData, job: JobRequirement) -> SkillGapAnalysis:
    corpus = _build_corpus(resume)
    matched, partial, missing = [], [], []
    for req in job.hard_skills + job.soft_skills:
        keys = _alias_keys(req.description)
        if any(k in corpus for k in keys):
            matched.append(SkillMatchItem(skill=req.description, matched=True, evidence="字面匹配"))
        elif any(_partial_hit(k, corpus) for k in keys):
            partial.append(SkillMatchItem(skill=req.description, matched=False, confidence=0.5, evidence="字面部分匹配"))
        else:
            missing.append(SkillMatchItem(skill=req.description, matched=False, evidence=None))
    total = len(matched) + len(partial) + len(missing)
    coverage = (len(matched) + 0.5 * len(partial)) / total if total else 0.0
    return SkillGapAnalysis(matched=matched, partial=partial, missing=missing, coverage=round(coverage, 4))


# ============================================================================
# 入口
# ============================================================================

def analyze_skill_gap(
    resume: ResumeData,
    job: JobRequirement,
    *,
    llm_client: Optional[LLMClient] = None,
    force_literal: bool = False,
) -> SkillGapAnalysis:
    """技能差距分析。

    Args:
        resume: 解析后的简历结构化数据。
        job: 解析后的岗位结构化要求。
        llm_client: 注入 LLM 客户端。传 None 时跳过语义匹配(等同 force_literal)。
        force_literal: 强制走字面匹配(用于性能对比 / 离线测试)。

    Returns:
        SkillGapAnalysis: 包含 matched / partial / missing 三类及 coverage。
    """
    if force_literal or llm_client is None:
        return _literal_skill_gap(resume, job)

    try:
        return _semantic_skill_gap(resume, job, llm_client)
    except ExtractError as exc:
        logger.warning("语义匹配失败,回退到字面匹配: %s", exc)
        return _literal_skill_gap(resume, job)
