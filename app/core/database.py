"""SQLAlchemy 2.0 异步数据库引擎.

- 单进程单引擎,延迟初始化(lazy)
- 通过 async_sessionmaker 工厂产出 AsyncSession
- 暴露 get_db() 用于 FastAPI 依赖注入
- 失败优雅降级:数据库不可用时不影响主分析流程(缓存层是可选的)
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database.url,
        echo=settings.debug,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        # PostgreSQL 异步驱动不需要预 ping
        pool_pre_ping=False,
    )


def get_engine() -> AsyncEngine:
    """获取或创建全局异步引擎."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
        logger.info("数据库引擎初始化完成: %s", get_settings().database.url.split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取全局 session 工厂."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖注入:获取异步数据库会话.

    使用方式:
        @router.get(...)
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """初始化数据库(创建表,仅用于开发/测试).

    生产环境使用 Alembic 迁移:alembic upgrade head
    """
    from app.models.cache import Base  # 避免循环引用

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构初始化完成")


async def close_db() -> None:
    """关闭数据库引擎(lifespan 退出时调用)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("数据库引擎已关闭")
