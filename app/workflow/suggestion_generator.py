"""建议生成器.

- 输入: 简历 + 岗位 + 匹配分析结果(综合证据)
- 输出: List[ResumeSuggestion],按 priority / type 排序
- 设计原则: 给模型"已结构化的证据"而非"自由发挥",降低幻觉
- 使用 chat_json + Pydantic Schema 强制结构化输出
"""
from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.extractors.llm_client import LLMClient
from app.models.job_requirement import JobRequirement
from app.models.resume import ResumeData
from app.models.suggestion import (
    MatchReport,
    ResumeSuggestion,
    SuggestionListOutput,
    SuggestionPriority,
)

logger = get_logger(__name__)


_SYSTEM_PROMPT = (
    "你是一名资深求职教练，擅长帮助候选人针对目标岗位优化简历。\n\n"
    "你的任务是根据简历原文、岗位要求和匹配分析结果，生成可执行的简历修改建议。\n\n"
    "核心要求（必须严格遵守）:\n"
    "1. 每条建议的 current 字段必须引用简历中的具体原文片段，不能为空\n"
    "   - 如果建议针对某段工作经历，引用该经历的描述原文\n"
    "   - 如果建议针对技能列表，引用当前技能列表内容\n"
    "   - 如果建议针对整体表达，引用最相关的段落\n"
    "2. 每条建议的 example 字段必须给出改写后的示例文本，不能为空\n"
    "   - 示例必须是完整的改写段落，不是\"例如：补充XXX\"\n"
    "   - 示例要自然融入关键词、量化数据、具体成果\n"
    "3. 每条建议的 reason 字段必须说明为什么需要这条修改，不能为空\n"
    "   - 必须引用具体的岗位要求或匹配分析结果\n"
    "   - 错误示例：\"需要补充\"\n"
    "   - 正确示例：\"岗位要求熟悉 Kafka 消息队列并有实战经验，但简历中未提及任何消息队列使用经历\"\n"
    "4. suggestion 字段必须具体可执行，不能是模板句式\n"
    "   - 错误示例：\"在技能列表中补充 Redis，并提供使用场景\"\n"
    "   - 正确示例：\"将技能列表中的'熟悉 Redis'改为独立条目，并在工作经历中补充 Redis 缓存设计的具体场景和性能提升数据\"\n"
    "5. 多个缺失关键词应合并为 1-2 条建议，不要逐个罗列\n"
    "   - 错误：10 条\"融入关键词 X\"的建议\n"
    "   - 正确：1 条\"在求职分析智能体项目描述中融入 Kafka、向量数据库、AI Agent 等关键词，例如：...\"\n"
    "6. 建议总数控制在 5-8 条，每条都有实质内容\n"
    "7. 优先覆盖 high priority 的硬技能缺口和经验不足问题\n\n"
    "输出格式: 必须输出 JSON 对象 {\"suggestions\": [...]}, 每条建议包含 type/priority/section/current/suggestion/example/reason 全部字段。\n"
    "不要追加任何解释文字或 Markdown 包装。"
)


def generate_suggestions(
    resume: ResumeData,
    job: JobRequirement,
    report: MatchReport,
    llm: LLMClient,
) -> List[ResumeSuggestion]:
    """调用 LLM 生成建议,并对结果做 schema 校验和排序."""
    user_prompt = _build_user_prompt(resume, job, report)
    try:
        result: SuggestionListOutput = llm.chat_json(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            schema=SuggestionListOutput,
            max_retries=2,
        )
    except Exception as exc:
        logger.warning(f"LLM 建议生成失败,使用回退: {exc}")
        return _fallback_suggestions(resume, job, report)
    return _sort_suggestions(result.suggestions)


def _build_resume_text(resume: ResumeData) -> str:
    """提取简历原文段落,供 LLM 引用.

    优先用 raw_text（用户简历原文），截取关键段落控制 token 量。
    如果 raw_text 为空，回退到结构化字段拼接。
    """
    if resume.raw_text and resume.raw_text.strip():
        text = resume.raw_text.strip()
        if len(text) > 3000:
            text = text[:3000] + "\n...(原文过长，已截断)"
        return text

    # 回退：从结构化字段拼接
    parts = []

    if resume.summary:
        parts.append(f"### 个人简介\n{resume.summary}")

    if resume.skills:
        skills_text = "\n".join(f"- {s}" for s in resume.skills)
        parts.append(f"### 技能列表\n{skills_text}")

    for w in resume.work_experience or []:
        w_text = f"### {w.position or ''} @ {w.company or ''}"
        if w.start_date or w.end_date:
            w_text += f" ({w.start_date or '?'} - {w.end_date or '至今'})"
        if w.description:
            w_text += f"\n{w.description}"
        if w.achievements:
            w_text += "\n成果: " + "; ".join(w.achievements)
        parts.append(w_text)

    for p in resume.projects or []:
        p_text = f"### {p.name or '项目'}"
        if p.role:
            p_text += f" ({p.role})"
        if p.description:
            p_text += f"\n{p.description}"
        if p.technologies:
            p_text += f"\n技术栈: {', '.join(p.technologies)}"
        parts.append(p_text)

    return "\n\n".join(parts) or "（无简历原文）"


def _build_job_text(job: JobRequirement) -> str:
    """格式化岗位信息."""
    parts = []
    if job.position:
        parts.append(f"### 岗位名称\n{job.position}")
    if job.company:
        parts.append(f"### 公司\n{job.company}")
    if job.responsibilities:
        parts.append(f"### 岗位职责\n{job.responsibilities}")
    if job.hard_skills:
        skills = "\n".join(f"- {r.description}" for r in job.hard_skills)
        parts.append(f"### 硬性技能要求\n{skills}")
    if job.soft_skills:
        skills = "\n".join(f"- {r.description}" for r in job.soft_skills)
        parts.append(f"### 软性技能要求\n{skills}")
    if job.experience:
        exps = "\n".join(f"- {r.description}" for r in job.experience)
        parts.append(f"### 经验要求\n{exps}")
    return "\n\n".join(parts) or "（无岗位信息）"


def _build_user_prompt(resume: ResumeData, job: JobRequirement, report: MatchReport) -> str:
    """构造完整 user prompt."""
    resume_text = _build_resume_text(resume)
    job_text = _build_job_text(job)

    sg = report.skill_gap
    ex = report.experience
    kw = report.keywords

    matched_skills = [s.skill for s in sg.matched]
    partial_skills = [s.skill for s in sg.partial]
    missing_skills = [s.skill for s in sg.missing]
    matched_kw = kw.matched or []
    missing_kw = kw.missing or []
    hard_gaps = report.hard_requirements_gaps

    return (
        "请基于以下信息，生成 5-8 条简历修改建议。\n\n"
        f"## 候选人简历原文\n\n{resume_text}\n\n"
        f"## 目标岗位\n\n{job_text}\n\n"
        "## 匹配分析结果\n\n"
        f"### 技能匹配\n"
        f"- 已命中: {matched_skills}\n"
        f"- 部分匹配: {partial_skills}\n"
        f"- 缺失: {missing_skills}\n"
        f"- 覆盖率: {sg.coverage}\n\n"
        f"### 经验匹配\n"
        f"- 要求年限: {ex.years_required}\n"
        f"- 估算年限: {ex.years_estimated}\n"
        f"- 备注: {ex.notes}\n\n"
        f"### 关键词匹配\n"
        f"- 已覆盖: {matched_kw}\n"
        f"- 未覆盖: {missing_kw}\n"
        f"- 覆盖率: {kw.coverage}\n\n"
        f"### 综合评分\n"
        f"- 分数: {report.overall_score}\n"
        f"- 评分理由: {report.score_reasoning}\n"
        f"- 亮点: {report.strengths}\n"
        f"- 短板: {report.weaknesses}\n\n"
        f"### 硬性要求差距\n{hard_gaps}\n\n"
        "请输出建议。"
    )


def _fallback_suggestions(
    resume: ResumeData,
    job: JobRequirement,
    report: MatchReport,
) -> List[ResumeSuggestion]:
    """LLM 失败时的规则回退."""
    from app.models.suggestion import SuggestionType, ResumeSection

    items: List[ResumeSuggestion] = []

    for s in report.skill_gap.missing[:3]:
        items.append(
            ResumeSuggestion(
                type=SuggestionType.CONTENT,
                priority=SuggestionPriority.HIGH,
                section=ResumeSection.SKILLS,
                suggestion=f"补充技能: {s.skill}",
                reason=f"岗位要求该技能但简历中缺失",
            )
        )

    if report.experience.years_required and (
        report.experience.years_estimated is None
        or report.experience.years_estimated < report.experience.years_required
    ):
        items.append(
            ResumeSuggestion(
                type=SuggestionType.QUANTIFY,
                priority=SuggestionPriority.HIGH,
                section=ResumeSection.WORK_EXPERIENCE,
                suggestion="量化工作经历中的成果和年限",
                reason=f"经验年限不足: 要求 {report.experience.years_required} 年",
            )
        )

    if report.keywords.missing:
        kw_list = ", ".join(report.keywords.missing[:5])
        items.append(
            ResumeSuggestion(
                type=SuggestionType.KEYWORD,
                priority=SuggestionPriority.MEDIUM,
                section=ResumeSection.OVERALL,
                suggestion=f"在简历中融入关键词: {kw_list}",
                reason="关键词覆盖率低，简历与 JD 语言契合度不足",
            )
        )

    return _sort_suggestions(items)


def _sort_suggestions(items: List[ResumeSuggestion]) -> List[ResumeSuggestion]:
    priority_rank = {
        SuggestionPriority.HIGH: 0,
        SuggestionPriority.MEDIUM: 1,
        SuggestionPriority.LOW: 2,
    }
    return sorted(items, key=lambda s: (priority_rank.get(s.priority, 99), s.section.value))
