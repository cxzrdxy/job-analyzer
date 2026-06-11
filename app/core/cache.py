"""分析缓存服务:save / load / list / delete / cleanup.

设计目标:
- 缓存写入失败不影响主分析流程(优雅降级)
- upsert 语义:相同 trace_id 重复写入会覆盖(用于重试)
- 提供列表分页和按 TTL 清理能力
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.cache import AnalysisCache

logger = get_logger(__name__)


def _extract_summary(
    resume_data: Optional[dict],
    job_requirement: Optional[dict],
    match_report: Optional[dict],
) -> tuple[Optional[str], Optional[str], float]:
    """从完整数据中提取摘要字段,避免列表查询时反序列化整个 JSONB."""
    resume_name: Optional[str] = None
    job_title: Optional[str] = None
    overall_score: float = 0.0

    if isinstance(resume_data, dict):
        resume_name = resume_data.get("name") or resume_name
    if isinstance(job_requirement, dict):
        job_title = (
            job_requirement.get("title")
            or job_requirement.get("position")
            or job_title
        )
    if isinstance(match_report, dict):
        try:
            overall_score = float(match_report.get("overall_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            overall_score = 0.0

    return resume_name, job_title, overall_score


async def save_analysis(
    session: AsyncSession,
    trace_id: str,
    *,
    resume_data: Optional[dict] = None,
    job_requirement: Optional[dict] = None,
    match_report: Optional[dict] = None,
    suggestions: Optional[list] = None,
    meta: Optional[dict] = None,
) -> None:
    """将分析结果写入缓存(upsert).

    策略:
    - 使用 session.merge():相同 trace_id 存在则更新,不存在则插入
    - 失败时抛出,由调用方决定是否降级
    """
    resume_name, job_title, overall_score = _extract_summary(
        resume_data, job_requirement, match_report
    )

    cache = AnalysisCache(
        trace_id=trace_id,
        created_at=datetime.utcnow(),
        resume_name=resume_name,
        job_title=job_title,
        overall_score=overall_score,
        resume_data=resume_data,
        job_requirement=job_requirement,
        match_report=match_report,
        suggestions=suggestions,
        meta=meta,
    )
    await session.merge(cache)
    await session.commit()
    logger.info(
        "缓存写入: trace_id=%s resume=%s job=%s score=%.1f",
        trace_id,
        resume_name or "—",
        job_title or "—",
        overall_score,
    )


async def load_analysis(
    session: AsyncSession,
    trace_id: str,
) -> Optional[dict[str, Any]]:
    """根据 trace_id 读取完整分析数据."""
    stmt = select(AnalysisCache).where(AnalysisCache.trace_id == trace_id)
    result = await session.execute(stmt)
    cache = result.scalar_one_or_none()
    if cache is None:
        return None
    return {
        "trace_id": cache.trace_id,
        "created_at": cache.created_at.isoformat() if cache.created_at else None,
        "resume_data": cache.resume_data,
        "job_requirement": cache.job_requirement,
        "match_report": cache.match_report,
        "suggestions": cache.suggestions,
        "meta": cache.meta,
    }


async def load_summary(
    session: AsyncSession,
    trace_id: str,
) -> Optional[dict[str, Any]]:
    """读取分析摘要(标量字段),用于面试题页面快速展示."""
    stmt = select(
        AnalysisCache.trace_id,
        AnalysisCache.created_at,
        AnalysisCache.resume_name,
        AnalysisCache.job_title,
        AnalysisCache.overall_score,
    ).where(AnalysisCache.trace_id == trace_id)
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        return None
    return {
        "trace_id": row.trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resume_name": row.resume_name,
        "job_title": row.job_title,
        "overall_score": float(row.overall_score or 0.0),
    }


async def list_analyses(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """分页列出所有缓存的分析(摘要信息)."""
    stmt = (
        select(
            AnalysisCache.trace_id,
            AnalysisCache.created_at,
            AnalysisCache.resume_name,
            AnalysisCache.job_title,
            AnalysisCache.overall_score,
        )
        .order_by(AnalysisCache.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [
        {
            "trace_id": row.trace_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "resume_name": row.resume_name,
            "job_title": row.job_title,
            "overall_score": float(row.overall_score or 0.0),
        }
        for row in result
    ]


async def delete_analysis(session: AsyncSession, trace_id: str) -> bool:
    """删除指定 trace_id 的缓存.返回是否实际删除了记录."""
    stmt = delete(AnalysisCache).where(AnalysisCache.trace_id == trace_id)
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) > 0


async def cleanup_expired(
    session: AsyncSession,
    ttl_days: Optional[int] = None,
) -> int:
    """清理超过 TTL 的过期缓存.返回删除的行数."""
    if ttl_days is None:
        ttl_days = get_settings().database.cache_ttl_days
    cutoff = datetime.utcnow() - timedelta(days=ttl_days)
    stmt = delete(AnalysisCache).where(AnalysisCache.created_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0
    if deleted > 0:
        logger.info("缓存清理: 删除 %d 条过期记录(TTL=%d 天)", deleted, ttl_days)
    return deleted


async def safe_save_analysis(
    trace_id: str,
    *,
    resume_data: Optional[dict] = None,
    job_requirement: Optional[dict] = None,
    match_report: Optional[dict] = None,
    suggestions: Optional[list] = None,
    meta: Optional[dict] = None,
) -> bool:
    """带降级的缓存写入:数据库不可用时返回 False,不抛异常.

    用于主分析流程末尾,确保缓存层故障不会影响分析结果的返回.
    """
    try:
        from app.core.database import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await save_analysis(
                session,
                trace_id,
                resume_data=resume_data,
                job_requirement=job_requirement,
                match_report=match_report,
                suggestions=suggestions,
                meta=meta,
            )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "缓存写入失败(已降级,不影响分析结果): trace_id=%s err=%s",
            trace_id,
            exc,
        )
        return False
