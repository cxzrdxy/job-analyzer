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
from app.workflow.progress import (
    INTERVIEW_STAGES,
    StageDef,
    compute_streaming_percent,
    get_current_stage,
    interview_stage_by_key,
    make_done_event,
    make_error_event,
    make_meta_event,
    make_progress_event,
    make_stage_end_event,
    make_stage_start_event,
    set_current_stage,
)

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
    focus: str = Field("balanced", description="侧重方向:balanced / technical / project / behavioral")
    question_count: int = Field(0, description="期望题数,0=自动(8-12)", ge=0, le=20)
    difficulty_bias: str = Field("", description="难度偏好:easy / medium / hard / 空=自动")
    force_regenerate: bool = Field(False, description="强制重新生成,忽略缓存")


# ---------------------------------------------------------------------------
# 流式事件工厂(与主分析一致的 NDJSON 格式)
# ---------------------------------------------------------------------------


def _json_line(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


async def _predict_stream_events(trace_id: str) -> AsyncIterator[bytes]:
    """面试题预测流式事件生成器.

    使用 progress.py 的 INTERVIEW_STAGES 定义,与主分析协议一致:
      0%-10%  — 读取缓存(load_cache)
      10%-30% — 构造 prompt(build_prompt)
      30%-95% — LLM 流式输出(predict,含 token 级进度)
      95%-99% — 校验与修正(validate)
    """
    t0 = time.monotonic()

    try:
        # ---- meta 事件 ----
        yield _json_line(make_meta_event(trace_id))
        # 重写 stages 为面试专用阶段
        meta_stages = [
            {"index": s.index, "key": s.key, "label": s.label, "span": [s.percent_start, s.percent_end]}
            for s in INTERVIEW_STAGES
        ]
        # 修正: meta 事件中的 stages 应使用面试专用阶段
        # 由于 make_meta_event 使用全局 STAGES,此处手动覆盖
        meta_override = make_meta_event(trace_id)
        meta_override["stages"] = meta_stages
        yield _json_line(meta_override)

        # ---- 阶段 0: load_cache ----
        load_stage = interview_stage_by_key("load_cache")
        assert load_stage is not None
        yield _json_line(make_stage_start_event(load_stage))
        set_current_stage(load_stage)

        factory = get_session_factory()
        async with factory() as session:
            cached = await load_analysis(session, trace_id)
        if cached is None:
            yield _json_line(make_error_event("load_cache", "not_found", f"分析结果不存在或已过期: {trace_id}"))
            return

        yield _json_line(make_stage_end_event(load_stage))

        # ---- 阶段 1: build_prompt ----
        build_stage = interview_stage_by_key("build_prompt")
        assert build_stage is not None
        yield _json_line(make_stage_start_event(build_stage))
        set_current_stage(build_stage)

        from app.services.interview_service import _SYSTEM_PROMPT, _build_user_prompt, _extract_risk_points

        risk_profile = _extract_risk_points(cached)
        prompt = _build_user_prompt(cached, risk_profile)
        pct = compute_streaming_percent(build_stage, "streaming", len(prompt))
        yield _json_line(make_progress_event(build_stage, pct, message=f"Prompt 已构建({len(prompt)} 字符)"))

        yield _json_line(make_stage_end_event(build_stage))

        # ---- 阶段 2: predict(LLM 流式) ----
        predict_stage = interview_stage_by_key("predict")
        assert predict_stage is not None
        yield _json_line(make_stage_start_event(predict_stage))
        set_current_stage(predict_stage)

        from app.extractors.llm_client import LLMClient
        from app.models.interview import InterviewPredictionOutput

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
                    # 使用 compute_streaming_percent 计算 token 级进度
                    pct = compute_streaming_percent(predict_stage, phase, chars)
                    msg = f"LLM 已生成 {chars} 字符" if chars else ""
                    yield _json_line(make_progress_event(predict_stage, pct, message=msg, chars=chars))
                elif kind == "done":
                    _, result = item
                    break
                elif kind == "app_error":
                    _, exc = item
                    yield _json_line(make_error_event("predict", exc.code, str(exc)))
                    return
                elif kind == "exception":
                    _, exc = item
                    logger.exception("面试题生成失败 trace_id=%s", trace_id)
                    yield _json_line(make_error_event("predict", "predict_error", str(exc)))
                    return
        finally:
            set_current_stage(None)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if result is None:
            yield _json_line(make_error_event("predict", "predict_error", "LLM 未返回结果"))
            return

        yield _json_line(make_stage_end_event(predict_stage))

        # ---- 阶段 3: validate ----
        validate_stage = interview_stage_by_key("validate")
        assert validate_stage is not None
        yield _json_line(make_stage_start_event(validate_stage))
        set_current_stage(validate_stage)

        from app.services.interview_service import _validate_questions, _build_correction_prompt
        from app.models.interview import QuestionPriority

        validation = _validate_questions(result)
        if not validation.passed:
            logger.warning("流式面试题校验失败 trace_id=%s issues=%s", trace_id, validation.issues)
            correction = _build_correction_prompt(validation.issues)
            corrected_prompt = prompt + correction
            yield _json_line(make_progress_event(validate_stage, validate_stage.half, message="校验未通过,触发修正重生成…"))
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: llm.chat_json(
                        system=_SYSTEM_PROMPT,
                        user=corrected_prompt,
                        schema=InterviewPredictionOutput,
                        max_retries=1,
                    ),
                )
                revalidation = _validate_questions(result)
                if not revalidation.passed:
                    logger.warning("修正后仍有问题 trace_id=%s issues=%s", trace_id, revalidation.issues)
            except Exception as exc:  # noqa: BLE001
                logger.warning("修正型重生成失败 trace_id=%s err=%s", trace_id, exc)

        # 按优先级排序
        _priority_order = {"high": 0, "medium": 1, "low": 2}
        result.questions.sort(key=lambda q: _priority_order.get(q.priority.value, 1))

        yield _json_line(make_stage_end_event(validate_stage))

        # ---- done ----
        duration_ms = (time.monotonic() - t0) * 1000

        from app.models.interview import PROMPT_VERSION, STRATEGY_VERSION

        done_data = {
            "trace_id": trace_id,
            "interview_questions": result.model_dump(),
            "prompt_version": PROMPT_VERSION,
            "strategy_version": STRATEGY_VERSION,
            "risk_profile": {
                "high_count": len(risk_profile.high),
                "medium_count": len(risk_profile.medium),
                "low_count": len(risk_profile.low),
            },
        }
        yield _json_line(make_done_event(done_data, duration_ms))

    except Exception as exc:  # noqa: BLE001
        logger.exception("面试题预测异常 trace_id=%s", trace_id)
        current = get_current_stage()
        yield _json_line(make_error_event(
            current.key if current else "unknown",
            "internal_error",
            str(exc),
        ))
    finally:
        set_current_stage(None)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/interview/predict")
async def predict_interview(req: InterviewPredictRequest):
    """生成面试题(非流式,等待 LLM 完成一次性返回)."""
    try:
        result = await get_interview_service().predict(
            req.trace_id,
            focus=req.focus,
            question_count=req.question_count,
            difficulty_bias=req.difficulty_bias,
            force_regenerate=req.force_regenerate,
        )
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
