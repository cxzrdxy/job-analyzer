"""统一 API 响应模型."""
from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构."""

    success: bool = True
    code: str = "ok"
    message: str = "ok"
    data: Optional[T] = None
    trace_id: Optional[str] = None


class AnalyzeRequestMeta(BaseModel):
    """分析请求的元数据,作为响应头部返回."""

    resume_chars: int = 0
    job_chars: int = 0
    used_provider: str = ""
    used_model: str = ""


class AnalysisResult(BaseModel):
    """对外暴露的分析结果."""

    meta: AnalyzeRequestMeta = Field(default_factory=AnalyzeRequestMeta)
    match_report: dict  # 使用 dict 以减少前向耦合,具体类型 MatchReport
    suggestions: List[dict] = Field(default_factory=list)
