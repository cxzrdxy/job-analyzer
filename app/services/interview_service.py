"""面试题预测服务.

核心策略(v2 — 风险点驱动):
1. 从数据库缓存读取历史分析数据
2. 提取并分层风险点(一级/二级/三级)
3. 基于风险点优先级构造增强 prompt
4. 调用 LLM 生成 8-12 道题
5. 后处理校验(题量/比例/重复/泛题)
6. 校验失败时触发修正型重生成
7. 返回带解释字段的预测结果

设计原则:
- 题目必须关联候选人的具体技能缺口或 JD 要求,禁止泛泛的通用题
- 一级风险点(硬技能缺失/经验硬伤)必须优先覆盖
- 每道题都必须有 reason 和 priority,可解释、可排序
- suggested_answer_direction 给出 3-5 个关键要点,非完整答案
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.cache import load_analysis, load_interview_prediction, safe_save_interview_prediction
from app.core.database import get_session_factory
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.interview import (
    PROMPT_VERSION,
    STRATEGY_VERSION,
    InterviewPredictionOutput,
    QuestionPriority,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 风险点模型
# ---------------------------------------------------------------------------


@dataclass
class RiskPoint:
    """单个风险点."""

    description: str
    level: str          # "high" / "medium" / "low"
    source: str         # "skill_gap" / "experience" / "keyword" / "hard_requirement" / "weakness"
    related_skill: str = ""
    evidence: str = ""


@dataclass
class RiskProfile:
    """风险点画像."""

    high: list[RiskPoint] = field(default_factory=list)
    medium: list[RiskPoint] = field(default_factory=list)
    low: list[RiskPoint] = field(default_factory=list)


def _extract_risk_points(cached: dict[str, Any]) -> RiskProfile:
    """从缓存数据中提取并分层风险点.

    分层规则:
    - 一级(high): 硬技能缺失(skill_gap.missing)、硬性要求差距(hard_requirements_gaps)、主要短板(weaknesses)
    - 二级(medium): 部分匹配技能(skill_gap.partial)、经验差距(experience.notes)、关键词缺口(keywords.missing)
    - 三级(low): 已匹配但可能被深问的技能(skill_gap.matched)、匹配亮点(strengths)
    """
    profile = RiskProfile()
    match_report = cached.get("match_report") or {}
    skill_gap = match_report.get("skill_gap") or {}
    experience = match_report.get("experience") or {}
    keywords = match_report.get("keywords") or {}

    # ---- 一级风险 ----

    # 硬技能缺失
    for item in (skill_gap.get("missing") or []):
        skill = item.get("skill", item.get("name", str(item))) if isinstance(item, dict) else str(item)
        evidence = item.get("evidence", "") if isinstance(item, dict) else ""
        profile.high.append(RiskPoint(
            description=f"缺失技能: {skill}",
            level="high",
            source="skill_gap",
            related_skill=skill,
            evidence=evidence,
        ))

    # 硬性要求差距
    for gap in (match_report.get("hard_requirements_gaps") or []):
        profile.high.append(RiskPoint(
            description=f"硬性要求差距: {gap}",
            level="high",
            source="hard_requirement",
        ))

    # 主要短板
    for w in (match_report.get("weaknesses") or []):
        profile.high.append(RiskPoint(
            description=f"主要短板: {w}",
            level="high",
            source="weakness",
        ))

    # ---- 二级风险 ----

    # 部分匹配技能
    for item in (skill_gap.get("partial") or []):
        skill = item.get("skill", item.get("name", str(item))) if isinstance(item, dict) else str(item)
        evidence = item.get("evidence", "") if isinstance(item, dict) else ""
        profile.medium.append(RiskPoint(
            description=f"部分匹配技能: {skill}",
            level="medium",
            source="skill_gap",
            related_skill=skill,
            evidence=evidence,
        ))

    # 经验差距说明
    for note in (experience.get("notes") or []):
        profile.medium.append(RiskPoint(
            description=f"经验差距: {note}",
            level="medium",
            source="experience",
        ))

    # 关键词缺口
    for kw in (keywords.get("missing") or []):
        profile.medium.append(RiskPoint(
            description=f"关键词缺口: {kw}",
            level="medium",
            source="keyword",
        ))

    # ---- 三级风险 ----

    # 已匹配技能(可能被深问)
    for item in (skill_gap.get("matched") or []):
        skill = item.get("skill", item.get("name", str(item))) if isinstance(item, dict) else str(item)
        evidence = item.get("evidence", "") if isinstance(item, dict) else ""
        profile.low.append(RiskPoint(
            description=f"已匹配技能(可能深问): {skill}",
            level="low",
            source="skill_gap",
            related_skill=skill,
            evidence=evidence,
        ))

    # 匹配亮点(项目追问)
    for s in (match_report.get("strengths") or []):
        profile.low.append(RiskPoint(
            description=f"匹配亮点(可能追问): {s}",
            level="low",
            source="weakness",  # 复用 source 字段,此处表示"来自匹配分析"
        ))

    return profile


# ---------------------------------------------------------------------------
# Prompt 模板(v2)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """你是一位资深技术面试官,熟悉互联网公司技术面试全流程.
你的任务是根据候选人简历与岗位要求的匹配分析结果,预测该候选人面试中可能被问到的题目.

核心原则:
1. 题目必须针对候选人的具体技能缺口或 JD 强相关要求,严禁生成通用题或泛泛开场题
2. 严格按风险点优先级出题:一级风险(高优先)必须重点覆盖,二级风险(中优先)补充,三级风险(低优先)仅在补足题量时使用
3. 每道题必须说明出题原因(reason),引用简历或 JD 中的证据
4. 输出严格的 JSON,符合给定的 JSON Schema
5. 不要在 JSON 之外输出任何解释
"""


def _build_user_prompt(cached: dict[str, Any], risk_profile: RiskProfile) -> str:
    """基于缓存数据与风险画像构造增强面试题 prompt.

    prompt 分 5 段:
    1. 候选人核心背景摘要
    2. 岗位核心要求摘要
    3. 风险点分层列表(核心增强)
    4. 项目与经验证据
    5. 输出规则与校验要求
    """
    match_report = cached.get("match_report") or {}
    resume_data = cached.get("resume_data") or {}
    job_requirement = cached.get("job_requirement") or {}

    # ---- 段 1: 候选人核心背景 ----
    name = resume_data.get("name", "未命名候选人")
    summary = resume_data.get("summary", "")
    projects = resume_data.get("projects") or []
    project_lines: list[str] = []
    for p in projects[:5]:
        pname = p.get("name") or "未命名项目"
        role = p.get("role") or ""
        techs = ", ".join(p.get("technologies") or [])
        highlights = p.get("highlights") or []
        hl_text = f"; 成果: {', '.join(str(h) for h in highlights[:3])}" if highlights else ""
        project_lines.append(f"- {pname}({role}): 技术栈=[{techs}]{hl_text}")
    projects_text = "\n".join(project_lines) or "（无）"

    work = resume_data.get("work_experience") or []
    work_lines: list[str] = []
    for w in work[:3]:
        company = w.get("company") or "未知公司"
        position = w.get("position") or ""
        work_lines.append(f"- {company} · {position}")
    work_text = "\n".join(work_lines) or "（无）"

    # ---- 段 2: 岗位核心要求 ----
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

    # ---- 段 3: 风险点分层列表 ----
    high_risks = "\n".join(
        f"- {rp.description}{' [证据: ' + rp.evidence + ']' if rp.evidence else ''}"
        for rp in risk_profile.high[:15]
    ) or "（无）"
    medium_risks = "\n".join(
        f"- {rp.description}{' [证据: ' + rp.evidence + ']' if rp.evidence else ''}"
        for rp in risk_profile.medium[:15]
    ) or "（无）"
    low_risks = "\n".join(
        f"- {rp.description}{' [证据: ' + rp.evidence + ']' if rp.evidence else ''}"
        for rp in risk_profile.low[:10]
    ) or "（无）"

    # ---- 段 4: 经验与关键词证据 ----
    experience = match_report.get("experience") or {}
    keywords = match_report.get("keywords") or {}
    exp_notes = "\n".join(f"- {n}" for n in (experience.get("notes") or [])) or "（无）"
    kw_missing = "\n".join(f"- {k}" for k in (keywords.get("missing") or [])) or "（无）"
    kw_matched = "\n".join(f"- {k}" for k in (keywords.get("matched") or [])) or "（无）"

    # ---- 组装 ----
    return f"""## 一、候选人核心背景

### 基本信息
- 姓名: {name}
- 摘要: {summary or '（无）'}

### 项目经历(精简)
{projects_text}

### 工作经验(精简)
{work_text}

## 二、岗位核心要求

### 职位
{title}

### 硬技能要求
{_req_desc(hard_skills)}

### 软技能要求
{_req_desc(soft_skills)}

### 关键职责
{_format_list(responsibilities)}

## 三、风险点分层(出题优先级依据)

### 一级风险(高优先 — 必须重点考察)
{high_risks}

### 二级风险(中优先 — 需补强)
{medium_risks}

### 三级风险(低优先 — 仅在补足题量时使用)
{low_risks}

## 四、经验与关键词证据

### 经验差距说明
{exp_notes}

### 缺失关键词(简历表达缺口)
{kw_missing}

### 已命中关键词
{kw_matched}

---

## 五、生成规则

请生成面试题,严格遵循:

1. **总题数 8-12 道**,按以下比例分配:
   - technical(技术题):4-6 道,优先针对一级和二级风险中的技能缺口
   - behavioral(行为题):2-3 道,基于 JD 软技能要求与经验差距
   - project(项目深挖):2-3 道,必须与候选人真实项目经历绑定
   - situational(情景题):0-1 道,仅当 JD 有明确场景要求时生成

2. **难度与优先级映射**:
   - 一级风险点 → difficulty=hard, priority=high
   - 二级风险点 → difficulty=medium 或 hard, priority=medium
   - 三级风险点 → difficulty=easy, priority=low

3. **每道题必须包含**:
   - category: technical / behavioral / project / situational
   - difficulty: easy / medium / hard
   - question: 用面试官口吻提问,具体、有深度,不超过 100 字
   - intent: 考察意图,说明此题测试的核心能力
   - suggested_answer_direction: 3-5 个关键答题要点,不要写完整答案,不超过 200 字
   - related_skill: 关联的技能缺口名称(如适用)
   - related_jd_requirement: 关联的 JD 要求原文(如适用)
   - reason: 出题原因,说明为什么预测这道题,对应哪项简历短板或 JD 要求
   - priority: high / medium / low,与风险等级一致
   - confidence: 0-1 的浮点数,预测可信度
   - evidence_from_resume: 简历中支撑此题的证据片段(如适用)
   - evidence_from_jd: JD 中支撑此题的证据片段(如适用)

4. **严格禁止**:
   - 生成通用开场题(如"请自我介绍")
   - 同一技能重复出多道几乎同义的题
   - question 字段与意图/技能不对应的题

5. **summary**: 2-3 句话的备考建议摘要,按优先级给出行动指导.

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
# 后处理校验
# ---------------------------------------------------------------------------

# 类别期望题量范围
_CATEGORY_RANGES: dict[str, tuple[int, int]] = {
    "technical": (4, 6),
    "behavioral": (2, 3),
    "project": (2, 3),
    "situational": (0, 1),
}

# 通用题关键词黑名单
_GENERIC_PATTERNS: list[str] = [
    "请自我介绍",
    "请介绍一下自己",
    "你的优点和缺点",
    "你的职业规划",
    "为什么选择我们公司",
    "你有什么想问的",
]


@dataclass
class ValidationResult:
    """校验结果."""

    passed: bool = True
    issues: list[str] = field(default_factory=list)


def _validate_questions(output: InterviewPredictionOutput) -> ValidationResult:
    """后处理校验 LLM 输出的面试题.

    校验项:
    - 总题量是否在 8-12 道
    - 各类别题量是否在合理范围
    - 是否存在重复题(基于 related_skill + category 组合)
    - 是否存在明显通用题
    - priority 与 difficulty 是否大致匹配
    """
    result = ValidationResult()
    questions = output.questions

    # 1. 总题量
    if len(questions) < 8 or len(questions) > 12:
        result.issues.append(
            f"题目总数 {len(questions)} 不在 8-12 范围内"
        )

    # 2. 各类别题量
    cat_counts: dict[str, int] = {}
    for q in questions:
        cat = q.category.value
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, (lo, hi) in _CATEGORY_RANGES.items():
        cnt = cat_counts.get(cat, 0)
        if cnt < lo:
            result.issues.append(f"{cat} 题数量不足: {cnt} < {lo}")
        elif cnt > hi:
            result.issues.append(f"{cat} 题数量过多: {cnt} > {hi}")

    # 3. 重复题检测(同一 related_skill + category 出现 >1 次)
    seen_keys: dict[str, int] = {}
    for q in questions:
        key = f"{q.category.value}:{q.related_skill or ''}"
        seen_keys[key] = seen_keys.get(key, 0) + 1
    for key, cnt in seen_keys.items():
        if cnt > 1 and key.split(":")[1]:
            result.issues.append(f"重复题: {key} 出现 {cnt} 次")

    # 4. 通用题检测
    for q in questions:
        q_text = q.question.lower()
        for pattern in _GENERIC_PATTERNS:
            if pattern in q_text:
                result.issues.append(
                    f"通用题: 「{q.question[:30]}…」匹配黑名单「{pattern}」"
                )
                break

    # 5. priority 与 difficulty 大致匹配
    _priority_diff_map: dict[str, set[str]] = {
        "high": {"hard"},
        "medium": {"medium", "hard"},
        "low": {"easy", "medium"},
    }
    for q in questions:
        allowed = _priority_diff_map.get(q.priority.value, set())
        if allowed and q.difficulty.value not in allowed:
            result.issues.append(
                f"优先级/难度不匹配: priority={q.priority.value} difficulty={q.difficulty.value}"
            )

    result.passed = len(result.issues) == 0
    return result


def _build_correction_prompt(issues: list[str]) -> str:
    """基于校验失败项构造修正提示."""
    issue_lines = "\n".join(f"- {i}" for i in issues)
    return f"""

---

**上一版输出存在以下问题,请修正后重新生成:**

{issue_lines}

请严格按照原始输入和规则重新生成,重点修正以上问题。
"""


# ---------------------------------------------------------------------------
# 公共服务
# ---------------------------------------------------------------------------


class InterviewService:
    """面试题预测服务."""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()

    async def predict(
        self,
        trace_id: str,
        *,
        focus: str = "balanced",
        question_count: int = 0,
        difficulty_bias: str = "",
        force_regenerate: bool = False,
    ) -> dict[str, Any]:
        """主入口:从缓存读取分析数据,生成面试题.

        流程:
        1. 尝试读取面试题缓存(除非 force_regenerate)
        2. 读取分析缓存
        3. 提取风险点
        4. 构造 prompt
        5. 调用 LLM
        6. 后处理校验
        7. 校验失败则修正型重生成(最多1次)
        8. 写入面试题缓存
        9. 返回结果

        参数:
        - focus: 侧重方向 balanced/technical/project/behavioral
        - question_count: 期望题数(0=自动 8-12)
        - difficulty_bias: 难度偏好 easy/medium/hard/""
        - force_regenerate: 强制重新生成(忽略缓存)

        抛出:
        - NotFoundError: 缓存不存在
        - ExtractError: LLM 输出无法解析
        """
        # 0. 尝试读取面试题缓存
        if not force_regenerate:
            try:
                factory = get_session_factory()
                async with factory() as session:
                    cached_prediction = await load_interview_prediction(
                        session, trace_id, PROMPT_VERSION,
                        focus=focus, question_count=question_count, difficulty_bias=difficulty_bias,
                    )
                if cached_prediction is not None:
                    logger.info("面试题缓存命中 trace_id=%s", trace_id)
                    cached_prediction["from_cache"] = True
                    return cached_prediction
            except Exception:  # noqa: BLE001
                pass  # 缓存不可用时静默降级

        # 1. 从数据库读取
        factory = get_session_factory()
        async with factory() as session:
            cached = await load_analysis(session, trace_id)
        if cached is None:
            raise NotFoundError(f"分析结果不存在或已过期: {trace_id}")

        # 2. 提取风险点
        risk_profile = _extract_risk_points(cached)

        # 3. 构造 prompt
        prompt = _build_user_prompt(cached, risk_profile)
        logger.info(
            "开始生成面试题 trace_id=%s prompt_len=%d risks=%d/%d/%d",
            trace_id,
            len(prompt),
            len(risk_profile.high),
            len(risk_profile.medium),
            len(risk_profile.low),
        )

        # 4. 调用 LLM
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

        # 5. 后处理校验
        validation = _validate_questions(result)
        if not validation.passed:
            logger.warning(
                "面试题校验失败 trace_id=%s issues=%s, 触发修正型重生成",
                trace_id,
                validation.issues,
            )
            # 6. 修正型重生成(最多1次)
            correction = _build_correction_prompt(validation.issues)
            corrected_prompt = prompt + correction
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: self._llm.chat_json(
                        system=_SYSTEM_PROMPT,
                        user=corrected_prompt,
                        schema=InterviewPredictionOutput,
                        max_retries=1,
                    ),
                )
                # 再次校验修正结果
                revalidation = _validate_questions(result)
                if not revalidation.passed:
                    logger.warning(
                        "修正后仍有问题 trace_id=%s issues=%s, 使用当前结果",
                        trace_id,
                        revalidation.issues,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "修正型重生成失败 trace_id=%s err=%s, 使用首次结果",
                    trace_id,
                    exc,
                )

        # 7. 按优先级排序问题(high → medium → low)
        _priority_order = {"high": 0, "medium": 1, "low": 2}
        result.questions.sort(
            key=lambda q: _priority_order.get(q.priority.value, 1)
        )

        logger.info(
            "面试题生成完成 trace_id=%s count=%d high=%d medium=%d low=%d",
            trace_id,
            len(result.questions),
            sum(1 for q in result.questions if q.priority == QuestionPriority.HIGH),
            sum(1 for q in result.questions if q.priority == QuestionPriority.MEDIUM),
            sum(1 for q in result.questions if q.priority == QuestionPriority.LOW),
        )

        output = {
            "trace_id": trace_id,
            "interview_questions": result.model_dump(),
            "prompt_version": PROMPT_VERSION,
            "strategy_version": STRATEGY_VERSION,
            "risk_profile": {
                "high_count": len(risk_profile.high),
                "medium_count": len(risk_profile.medium),
                "low_count": len(risk_profile.low),
            },
            "from_cache": False,
        }

        # 8. 异步写入缓存(不阻塞返回)
        await safe_save_interview_prediction(
            trace_id, output, PROMPT_VERSION,
            focus=focus, question_count=question_count, difficulty_bias=difficulty_bias,
        )

        return output
