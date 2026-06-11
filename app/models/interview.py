"""面试题预测相关数据模型.

题目四类:
- technical:       技术题(优先针对 missing/partial 技能)
- behavioral:      行为题(基于 JD 软技能要求)
- project:         项目深挖题(基于候选人项目经历中的技术栈与成果)
- situational:     情景题(仅当 JD 有明确场景要求时生成)

难度三档:easy / medium / hard
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QuestionCategory(str, Enum):
    """题目类别."""

    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    PROJECT = "project"  # project_deep_dive 的简写
    SITUATIONAL = "situational"


class Difficulty(str, Enum):
    """难度等级."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterviewQuestion(BaseModel):
    """单道面试题."""

    category: QuestionCategory = Field(
        ...,
        description="题目类别:technical / behavioral / project / situational",
    )
    difficulty: Difficulty = Field(..., description="难度等级:easy / medium / hard")
    question: str = Field(..., description="面试题原文")
    intent: str = Field(..., description="考察意图:面试官想通过此题测试什么")
    suggested_answer_direction: str = Field(
        ...,
        description="建议答题方向:3-5 个关键要点,非完整答案",
    )
    related_skill: Optional[str] = Field(
        None,
        description="此题针对的技能缺口(来自 skill_gap.missing 或 partial)",
    )
    related_jd_requirement: Optional[str] = Field(
        None,
        description="此题关联的 JD 要求原文",
    )


class InterviewPredictionOutput(BaseModel):
    """面试题预测输出.

    总题量 8-12 道,按以下比例分配(由 prompt 约束):
    - 技术题 4-6 道
    - 行为题 2-3 道
    - 项目深挖 2-3 道
    - 情景题 0-1 道
    """

    questions: list[InterviewQuestion] = Field(
        ...,
        description="预测面试题列表,8-12 道",
    )
    summary: str = Field(..., description="整体备考建议摘要,2-3 句话")


# 类别中文标签(前端展示)
CATEGORY_LABELS: dict[str, str] = {
    QuestionCategory.TECHNICAL.value: "技术题",
    QuestionCategory.BEHAVIORAL.value: "行为题",
    QuestionCategory.PROJECT.value: "项目深挖",
    QuestionCategory.SITUATIONAL.value: "情景题",
}

# 难度中文标签
DIFFICULTY_LABELS: dict[str, str] = {
    Difficulty.EASY.value: "简单",
    Difficulty.MEDIUM.value: "中等",
    Difficulty.HARD.value: "困难",
}
