"""面试题预测服务.

核心策略:
- 从数据库缓存读取历史分析数据(resume_data / job_requirement / match_report)
- 构造针对性 prompt,只调用一次 LLM 生成 8-12 道题
- 失败时由 LLMClient 自动重试一次,仍失败则抛出 ExtractError

设计原则(沿用 v1 方案的设计要点):
- 题目必须关联候选人的具体技能缺口或 JD 要求,禁止泛泛的通用题
- missing 技能出 hard 题,partial 技能出 medium/hard 题,matched 仅在补足题量时出 easy 题
- suggested_answer_direction 给出 3-5 个关键要点,非完整答案
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.core.cache import load_analysis
from app.core.database import get_session_factory
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.interview import InterviewPredictionOutput

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """你是一位资深技术面试官,熟悉互联网公司技术面试全流程.
你的任务是根据候选人简历与岗位要求的匹配分析结果,预测该候选人面试中可能被问到的题目.
要求:
1. 题目必须针对候选人的具体技能缺口(missing/partial)或 JD 强相关要求,严禁生成通用题
2. 输出严格的 JSON,符合给定的 JSON Schema
3. 不要在 JSON 之外输出任何解释
"""


def _build_user_prompt(cached: dict[str, Any]) -> str:
    """基于缓存数据构造面试题 prompt."""
    match_report = cached.get("match_report") or {}
    skill_gap = match_report.get("skill_gap") or {}
    matched_skills = skill_gap.get("matched") or []
    partial_skills = skill_gap.get("partial") or []
    missing_skills = skill_gap.get("missing") or []

    resume_data = cached.get("resume_data") or {}
    job_requirement = cached.get("job_requirement") or {}

    # 项目经历精简摘要(只取 name/role/technologies,避免 token 浪费)
    projects = resume_data.get("projects") or []
    project_lines: list[str] = []
    for p in projects[:5]:
        name = p.get("name") or "未命名项目"
        role = p.get("role") or ""
        techs = ", ".join(p.get("technologies") or [])
        project_lines.append(
            f"- {name}({role}): 技术栈=[{techs}]"
        )
    projects_text = "\n".join(project_lines) or "（无）"

    # 工作经验精简摘要
    work = resume_data.get("work_experience") or []
    work_lines: list[str] = []
    for w in work[:3]:
        company = w.get("company") or "未知公司"
        position = w.get("position") or ""
        work_lines.append(f"- {company} · {position}")
    work_text = "\n".join(work_lines) or "（无）"

    # 岗位要求
    title = job_requirement.get("title") or job_requirement.get("position") or "未指定"
    hard_skills = job_requirement.get("hard_skills") or []
    soft_skills = job_requirement.get("soft_skills") or []
    responsibilities = job_requirement.get("responsibilities") or []

    def _req_desc(items: list) -> str:
        if not items:
            return "（无）"
        return "\n".join(
            f"- {r.get('description', '') if isinstance(r, dict) else str(r)}"
            for r in items[:10]
        )

    return f"""## 候选人技能匹配结果

### 缺失技能(missing — 必须重点考察)
{_format_list(missing_skills)}

### 部分匹配技能(partial — 需补强)
{_format_list(partial_skills)}

### 已匹配技能(matched — 仅在补足题量时使用)
{_format_list(matched_skills)}

## 候选人项目经历(精简)
{projects_text}

## 候选人工作经验(精简)
{work_text}

## 岗位要求

### 职位
{title}

### 硬技能要求
{_req_desc(hard_skills)}

### 软技能要求
{_req_desc(soft_skills)}

### 关键职责
{_format_list(responsibilities)}

---

## 生成规则

请生成面试题,严格遵循:

1. **总题数 8-12 道**,按以下比例分配:
   - technical(技术题):4-6 道,优先针对 missing 和 partial 技能
   - behavioral(行为题):2-3 道,基于 JD 软技能要求
   - project(项目深挖):2-3 道,基于候选人项目经历中的技术栈与成果
   - situational(情景题):0-1 道,仅当 JD 有明确场景要求时生成

2. **难度分配原则**:
   - missing 技能 → hard
   - partial 技能 → medium 或 hard
   - matched 技能 → easy(仅用于补足题量)

3. **每道题必须包含**:
   - category: technical / behavioral / project / situational
   - difficulty: easy / medium / hard
   - question: 用面试官口吻提问,具体、有深度,不超过 100 字
   - intent: 考察意图,说明此题测试的核心能力
   - suggested_answer_direction: 3-5 个关键答题要点,不要写完整答案,不超过 200 字
   - related_skill: 关联的技能缺口名称(如适用)
   - related_jd_requirement: 关联的 JD 要求原文(如适用)

4. **summary**: 2-3 句话的备考建议摘要.

题目措辞需符合真实面试场景,避免过于学术化或脱离实际.
"""


def _format_list(items: Any) -> str:
    """把列表/嵌套结构格式化为多行字符串."""
    if not items:
        return "（无）"
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return "\n".join(
            f"- {it.get('skill', it.get('name', str(it)))}"
            for it in items[:20]
        )
    if isinstance(items, list):
        return "\n".join(f"- {x}" for x in items[:20])
    return str(items)


# ---------------------------------------------------------------------------
# 公共服务
# ---------------------------------------------------------------------------


class InterviewService:
    """面试题预测服务."""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()

    async def predict(self, trace_id: str) -> dict[str, Any]:
        """主入口:从缓存读取分析数据,生成面试题.

        抛出:
        - NotFoundError: 缓存不存在
        - ExtractError: LLM 输出无法解析
        """
        # 1. 从数据库读取
        factory = get_session_factory()
        async with factory() as session:
            cached = await load_analysis(session, trace_id)
        if cached is None:
            raise NotFoundError(f"分析结果不存在或已过期: {trace_id}")

        # 2. 构造 prompt
        prompt = _build_user_prompt(cached)
        logger.info("开始生成面试题 trace_id=%s prompt_len=%d", trace_id, len(prompt))

        # 3. 调用 LLM(失败时 LLMClient 内部自动重试一次)
        # chat_json 是同步方法,用 run_in_executor 避免阻塞事件循环
        loop = asyncio.get_running_loop()
        result: InterviewPredictionOutput = await loop.run_in_executor(
            None,
            lambda: self._llm.chat_json(
                system=_SYSTEM_PROMPT,
                user=prompt,
                schema=InterviewPredictionOutput,
                max_retries=1,
            ),
        )

        logger.info(
            "面试题生成完成 trace_id=%s count=%d",
            trace_id,
            len(result.questions),
        )

        return {
            "trace_id": trace_id,
            "interview_questions": result.model_dump(),
        }
