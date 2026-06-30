"""分析结果缓存 ORM 模型.

设计要点:
- 使用 JSONB 存储 Pydantic 对象的序列化结果,避免列爆炸
- 摘要字段(候选人姓名/岗位/综合评分)拆为标量列,列表页查询时不需要反序列化整个 JSONB
- trace_id 为主键,UUID v4 格式,长度 36
- 索引:created_at(用于 TTL 清理 + 时间排序),job_title(用于按岗位过滤)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """ORM 基类."""

    pass


class AnalysisCache(Base):
    """分析结果缓存表.

    用于:
    1. 面试题预测快速读取分析数据(避免重复解析)
    2. 历史分析列表查询
    3. 二期 RAG / 个性化题库扩展
    """

    __tablename__ = "analysis_cache"

    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # ---- 摘要字段(标量列,用于列表查询) ----
    resume_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # ---- 完整数据(JSONB 存储 Pydantic 序列化结果) ----
    resume_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    job_requirement: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    match_report: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    suggestions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # ---- 扩展元数据 ----
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_analysis_cache_created_at", "created_at"),
        Index("ix_analysis_cache_job_title", "job_title"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AnalysisCache trace_id={self.trace_id!r} "
            f"resume={self.resume_name!r} job={self.job_title!r} "
            f"score={self.overall_score:.1f}>"
        )


class InterviewCache(Base):
    """面试题预测结果缓存表.

    用于:
    1. 避免同一分析结果重复调用 LLM 生成面试题
    2. 按 prompt_version 区分不同生成策略的输出(支持 A/B 对比)
    3. 为论文实验提供可追溯的预测结果数据
    """

    __tablename__ = "interview_cache"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v2")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # ---- 完整预测结果(JSONB) ----
    prediction_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_interview_cache_trace_id", "trace_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<InterviewCache id={self.id!r} trace_id={self.trace_id!r} "
            f"prompt_version={self.prompt_version!r}>"
        )
