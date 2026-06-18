"""错误码单元测试."""
from __future__ import annotations

from tests.runner import unit
from app.core.errors import (
    AppError,
    ExtractError,
    ParseError,
    WorkflowError,
    UnsupportedFileTypeError,
    FileTooLargeError,
)


@unit
def test_app_error_http_status():
    """AppError 应映射到 http_status."""
    e = AppError("test", code="x", http_status=418)
    assert e.http_status == 418
    assert e.code == "x"
    assert str(e) == "test"


@unit
def test_extract_error_default_status():
    """ExtractError 默认 502(Bad Gateway)."""
    e = ExtractError("LLM 调用失败")
    assert e.http_status == 502
    assert e.code == "extract_error"


@unit
def test_parse_error_status():
    """ParseError 默认 422."""
    e = ParseError("解析失败")
    assert e.http_status == 422
    assert e.code == "parse_error"


@unit
def test_workflow_error_status():
    """WorkflowError 默认 500."""
    e = WorkflowError("工作流失败")
    assert e.http_status == 500
    assert e.code == "workflow_error"


@unit
def test_unsupported_file_type():
    """UnsupportedFileTypeError 415."""
    e = UnsupportedFileTypeError(".xlsx")
    assert e.http_status == 415


@unit
def test_file_too_large():
    """FileTooLargeError 413."""
    e = FileTooLargeError("超过 10 MB")
    assert e.http_status == 413


@unit
def test_error_inheritance():
    """所有自定义错误应当继承 AppError."""
    for cls in (ExtractError, ParseError, WorkflowError,
                UnsupportedFileTypeError, FileTooLargeError):
        assert issubclass(cls, AppError)