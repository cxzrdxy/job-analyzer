"""FastAPI 路由."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.core.logging import get_logger
from app.models.response import AnalysisResult, AnalyzeRequestMeta, ApiResponse
from app.services.analyzer import AnalyzerService

logger = get_logger(__name__)

router = APIRouter()
_service: Optional[AnalyzerService] = None
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def get_service() -> AnalyzerService:
    global _service
    if _service is None:
        _service = AnalyzerService()
    return _service


def _validate_upload(file: UploadFile) -> None:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.upload.allowed_extensions:
        raise UnsupportedFileTypeError(f"文件类型 {suffix} 不被支持")
    if file.content_type and file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise UnsupportedFileTypeError(f"文件内容类型 {file.content_type} 不被支持")


async def _read_with_limit(file: UploadFile) -> bytes:
    settings = get_settings()
    max_bytes = settings.upload.max_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(
                f"文件超过 {settings.upload.max_size_mb} MB 限制,实际已读取 {total} 字节"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/analyze", response_model=ApiResponse[AnalysisResult])
async def analyze_resume(
    resume: UploadFile = File(..., description="简历文件 (PDF/DOCX)"),
    job_description: Optional[str] = Form(None, description="岗位 JD 文本"),
    job_file: Optional[UploadFile] = File(None, description="岗位 JD 文件"),
    trace_id: Optional[str] = Form(None),
):
    """分析简历与岗位匹配度,返回优化建议.

    - `resume`: 必传,支持 PDF / DOCX / TXT
    - `job_description` 与 `job_file` 二选一
    """
    try:
        _validate_upload(resume)
        if job_file is not None:
            _validate_upload(job_file)

        resume_bytes = await _read_with_limit(resume)
        job_bytes = await _read_with_limit(job_file) if job_file is not None else None

        if not job_description and job_bytes is None:
            raise HTTPException(status_code=400, detail="请提供岗位 JD 文本或 JD 文件")
        if job_description and job_bytes is not None:
            raise HTTPException(status_code=400, detail="job_description 和 job_file 只能二选一")

        result = await get_service().analyze(
            resume_bytes=resume_bytes,
            resume_suffix=Path(resume.filename or "resume.pdf").suffix,
            job_text=job_description,
            job_bytes=job_bytes,
            job_suffix=Path(job_file.filename or "job.txt").suffix if job_file else ".txt",
            trace_id=trace_id or str(uuid.uuid4()),
        )
    except AppError as exc:
        logger.warning("分析失败: %s (trace_id=%s)", exc, trace_id)
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": str(exc)})
    except HTTPException:
        raise

    response_data = AnalysisResult(
        meta=AnalyzeRequestMeta(**result["meta"]),
        match_report=result["match_report"] or {},
        suggestions=result["suggestions"],
    )
    return ApiResponse[AnalysisResult](
        success=True,
        code="ok",
        message="分析完成",
        data=response_data,
        trace_id=result["trace_id"],
    )


@router.post("/analyze/stream")
async def analyze_resume_stream(
    resume: UploadFile = File(..., description="简历文件 (PDF/DOCX)"),
    job_description: Optional[str] = Form(None, description="岗位 JD 文本"),
    job_file: Optional[UploadFile] = File(None, description="岗位 JD 文件"),
    trace_id: Optional[str] = Form(None),
):
    """流式分析简历与岗位匹配度,NDJSON 逐行推送进度事件.

    事件类型: meta / stage_start / progress / stage_end / done / error
    与同步接口入参一致,老接口行为不变.
    """
    try:
        _validate_upload(resume)
        if job_file is not None:
            _validate_upload(job_file)

        resume_bytes = await _read_with_limit(resume)
        job_bytes = await _read_with_limit(job_file) if job_file is not None else None

        if not job_description and job_bytes is None:
            raise HTTPException(status_code=400, detail="请提供岗位 JD 文本或 JD 文件")
        if job_description and job_bytes is not None:
            raise HTTPException(status_code=400, detail="job_description 和 job_file 只能二选一")

        event_generator = get_service().analyze_stream(
            resume_bytes=resume_bytes,
            resume_suffix=Path(resume.filename or "resume.pdf").suffix,
            job_text=job_description,
            job_bytes=job_bytes,
            job_suffix=Path(job_file.filename or "job.txt").suffix if job_file else ".txt",
            trace_id=trace_id or str(uuid.uuid4()),
        )
        return StreamingResponse(
            event_generator,
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except AppError as exc:
        # 同步错误(如校验失败)返回单行 error NDJSON
        import json

        error_line = (
            json.dumps(
                {"type": "error", "stage": "upload", "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        return StreamingResponse(
            iter([error_line]),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except HTTPException:
        raise


@router.get("/health", response_model=ApiResponse[dict])
async def health() -> ApiResponse[dict]:
    return ApiResponse[dict](
        success=True,
        code="ok",
        message="ok",
        data={"status": "up"},
    )


@router.get("/info", response_model=ApiResponse[dict])
async def info() -> ApiResponse[dict]:
    """服务元信息,供根路径展示使用."""
    from app.core.config import get_settings

    settings = get_settings()
    return ApiResponse[dict](
        success=True,
        code="ok",
        message="ok",
        data={
            "name": settings.app_name,
            "version": settings.version,
            "provider": settings.llm.provider,
            "model": settings.llm.model,
            "endpoints": {
                "analyze": "POST /api/v1/analyze",
                "health": "GET /api/v1/health",
                "docs": "GET /docs",
                "openapi": "GET /openapi.json",
            },
        },
    )
