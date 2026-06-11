"""通用异常定义.

将领域错误集中在一处,便于 API 层统一返回和日志追踪.
"""
from __future__ import annotations


class AppError(Exception):
    """业务基类异常."""

    code: str = "app_error"
    http_status: int = 500

    def __init__(self, message: str, *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status


class FileTooLargeError(AppError):
    code = "file_too_large"
    http_status = 413


class UnsupportedFileTypeError(AppError):
    code = "unsupported_file_type"
    http_status = 415


class ParseError(AppError):
    """文档解析失败,如损坏/加密/OCR 不可用."""

    code = "parse_error"
    http_status = 422


class ExtractError(AppError):
    """LLM 结构化抽取失败."""

    code = "extract_error"
    http_status = 502


class WorkflowError(AppError):
    code = "workflow_error"
    http_status = 500


class NotFoundError(AppError):
    """资源不存在(如缓存项、面试题记录等)."""

    code = "not_found"
    http_status = 404
