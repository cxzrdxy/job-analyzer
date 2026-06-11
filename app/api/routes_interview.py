"""面试题预测与缓存管理 API.

端点列表:
- POST /api/v1/interview/predict        : 生成面试题(非流式)
- POST /api/v1/interview/predict/stream : 生成面试题(SSE/NDJSON 流式)
- GET  /api/v1/cache                    : 列出所有缓存的分析
- GET  /api/v1/cache/{trace_id}         : 获取单次分析的摘要信息
- DELETE /api/v1/cache/{trace_id}       : 删除单次缓存
- DELETE /api/v1/cache                  : 全量清理(慎用)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.cache import (
    delete_analysis,
    list_analyses,
    load_analysis,
)
from app.core.database import get_session_factory
from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger
from app.models.response import ApiResponse
from app.services.interview_service import InterviewService

logger = get_logger(__name__)

router = APIRouter()
_service: Optional[InterviewService] = None


def get_interview_service() -> InterviewService:
    global _service
    if _service is None:
        _service = InterviewService()
    return _service


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class InterviewPredictRequest(BaseModel):
    """面试题预测请求."""

    trace_id: str = Field(..., description="之前分析结果的 trace_id")


# ---------------------------------------------------------------------------
# 流式事件工厂(与主分析一致的 NDJSON 格式)
# ---------------------------------------------------------------------------


def _json_line(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def _stage_event(stage: str, percent: float, message: str = "") -> bytes:
    return _json_line(
        {
            "type": "progress",
            "stage": stage,
            "percent": round(percent, 1),
            "message": message,
        }
    )


def _done_event(data: dict, duration_ms: float) -> bytes:
    return _json_line(
        {
            "type": "done",
            "data": data,
            "duration_ms": round(duration_ms, 1),
        }
    )


def _error_event(stage: str, code: str, message: str) -> bytes:
    return _json_line(
        {"type": "error", "stage": stage, "code": code, "message": message}
    )


async def _predict_stream_events(trace_id: str) -> AsyncIterator[bytes]:
    """面试题预测流式事件生成器.

    阶段:
      0% — 读取缓存
      30% — 构造 prompt
      40%–95% — LLM 流式输出(progress 事件)
      100% — done
    """
    t0 = time.monotonic()
    stage_key = "predict"

    try:
        # ---- 0% — meta ----
        yield _json_line(
            {
                "type": "meta",
                "trace_id": trace_id,
                "stage": stage_key,
                "stages": [{"key": stage_key, "label": "预测面试题", "percent_range": [0, 100]}],
            }
        )
        yield _json_line(
            {"type": "stage_start", "stage": stage_key, "label": "预测面试题"}
        )

        # ---- 10% — 读取缓存 ----
        yield _stage_event(stage_key, 10, "读取分析缓存…")
        factory = get_session_factory()
        async with factory() as session:
            cached = await load_analysis(session, trace_id)
        if cached is None:
            yield _error_event(stage_key, "not_found", f"分析结果不存在或已过期: {trace_id}")
            return

        from app.services.interview_service import _SYSTEM_PROMPT, _build_user_prompt

        prompt = _build_user_prompt(cached)
        yield _stage_event(stage_key, 30, f"Prompt 已构建({len(prompt)} 字符)")

        # ---- 40%–95% — LLM 流式调用(带 progress 回调) ----
        from app.extractors.llm_client import LLMClient
        from app.models.interview import InterviewPredictionOutput
        from app.workflow.progress import set_current_stage_shared, get_current_stage_shared

        stage_obj = _MockStage(stage_key, "预测面试题", 0, 100)
        set_current_stage_shared(stage_obj)

        llm = LLMClient()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        def progress_cb(phase: str, info: dict) -> None:
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    ("progress", phase, info),
                )
            except (RuntimeError, asyncio.QueueFull):
                pass

        async def run_llm() -> None:
            try:
                # chat_json 走流式路径(progress_cb 存在)
                output = await loop.run_in_executor(
                    None,
                    lambda: llm.chat_json(
                        system=_SYSTEM_PROMPT,
                        user=prompt,
                        schema=InterviewPredictionOutput,
                        max_retries=1,
                        progress_callback=progress_cb,
                    ),
                )
                await queue.put(("done", output))
            except AppError as exc:
                await queue.put(("app_error", exc))
            except Exception as exc:  # noqa: BLE001
                await queue.put(("exception", exc))

        task = asyncio.create_task(run_llm())
        result: Optional[InterviewPredictionOutput] = None

        try:
            while True:
                item = await queue.get()
                kind = item[0]
                if kind == "progress":
                    _, phase, info = item
                    chars = info.get("chars", 0)
                    # 把字符数映射到 40%–95%
                    # 经验值:一次完整输出约 2000-4000 字符
                    pct = 40 + min(55, (chars / 4000) * 55)
                    yield _stage_event(stage_key, pct, f"LLM 已生成 {chars} 字符")
                elif kind == "done":
                    _, result = item
                    break
                elif kind == "app_error":
                    _, exc = item
                    yield _error_event(stage_key, exc.code, str(exc))
                    return
                elif kind == "exception":
                    _, exc = item
                    logger.exception("面试题生成失败 trace_id=%s", trace_id)
                    yield _error_event(stage_key, "predict_error", str(exc))
                    return
        finally:
            set_current_stage_shared(None)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if result is None:
            yield _error_event(stage_key, "predict_error", "LLM 未返回结果")
            return

        # ---- 100% — done ----
        yield _stage_event(stage_key, 100, "生成完成")
        yield _json_line({"type": "stage_end", "stage": stage_key})
        duration_ms = (time.monotonic() - t0) * 1000
        yield _done_event(
            {
                "trace_id": trace_id,
                "interview_questions": result.model_dump(),
            },
            duration_ms,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("面试题预测异常 trace_id=%s", trace_id)
        yield _error_event(stage_key, "internal_error", str(exc))


# 用一个内部类避免引入 StageDef 的依赖
class _MockStage:
    def __init__(self, key: str, label: str, percent_start: int, percent_end: int) -> None:
        self.key = key
        self.label = label
        self.percent_start = percent_start
        self.percent_end = percent_end


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/interview/predict")
async def predict_interview(req: InterviewPredictRequest):
    """生成面试题(非流式,等待 LLM 完成一次性返回)."""
    try:
        result = await get_interview_service().predict(req.trace_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        )
    except AppError as exc:
        logger.warning("面试题生成失败: %s", exc)
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001 — 缓存/数据库不可用时降级
        logger.warning("面试题预测异常(可能是缓存不可用): %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"code": "service_unavailable", "message": f"服务暂时不可用: {exc}"},
        )
    return ApiResponse(
        success=True,
        code="ok",
        message="ok",
        data=result,
        trace_id=req.trace_id,
    )


@router.post("/interview/predict/stream")
async def predict_interview_stream(req: InterviewPredictRequest):
    """生成面试题(NDJSON 流式,与主分析接口事件格式一致)."""
    return StreamingResponse(
        _predict_stream_events(req.trace_id),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cache")
async def list_cache(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出所有缓存的分析(摘要信息,分页)."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            items = await list_analyses(session, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        logger.warning("缓存列表查询失败: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"code": "cache_unavailable", "message": f"缓存服务不可用: {exc}"},
        )
    return ApiResponse(success=True, code="ok", message="ok", data={"items": items, "limit": limit, "offset": offset})


@router.get("/cache/{trace_id}")
async def get_cache(trace_id: str):
    """获取单次分析的全量数据(resume_data / job_requirement / match_report / suggestions / meta)."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            data = await load_analysis(session, trace_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("缓存读取失败 trace_id=%s: %s", trace_id, exc)
        raise HTTPException(
            status_code=503,
            detail={"code": "cache_unavailable", "message": f"缓存服务不可用: {exc}"},
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"分析结果不存在: {trace_id}"},
        )
    return ApiResponse(success=True, code="ok", message="ok", data=data)


@router.delete("/cache/{trace_id}")
async def delete_cache(trace_id: str):
    """删除单次缓存.返回是否实际删除."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            deleted = await delete_analysis(session, trace_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("缓存删除失败 trace_id=%s: %s", trace_id, exc)
        raise HTTPException(
            status_code=503,
            detail={"code": "cache_unavailable", "message": f"缓存服务不可用: {exc}"},
        )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"分析结果不存在: {trace_id}"},
        )
    return ApiResponse(success=True, code="ok", message="deleted", data={"trace_id": trace_id, "deleted": True})


@router.delete("/cache")
async def cleanup_cache_endpoint():
    """清理过期缓存(基于 CACHE_TTL_DAYS)."""
    from app.core.cache import cleanup_expired

    try:
        factory = get_session_factory()
        async with factory() as session:
            deleted = await cleanup_expired(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("缓存清理失败: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"code": "cache_unavailable", "message": f"缓存服务不可用: {exc}"},
        )
    return ApiResponse(success=True, code="ok", message="cleaned", data={"deleted": deleted})
