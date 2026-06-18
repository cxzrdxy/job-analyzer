"""配置单元测试."""
from __future__ import annotations

from tests.runner import unit
from app.core.config import get_settings, AppSettings, LLMSettings, UploadSettings


@unit
def test_settings_singleton():
    """get_settings 应当返回单例."""
    a = get_settings()
    b = get_settings()
    assert a is b


@unit
def test_llm_settings_provider_default():
    """provider 默认为 deepseek/openai,model 默认值非空."""
    s = get_settings()
    assert s.llm.provider in {"deepseek", "openai"}
    assert s.llm.model != ""
    assert s.llm.timeout > 0


@unit
def test_upload_settings_defaults():
    """上传配置默认 .pdf/.docx/.txt."""
    s = get_settings()
    assert ".pdf" in s.upload.allowed_extensions
    assert ".docx" in s.upload.allowed_extensions
    assert ".txt" in s.upload.allowed_extensions
    assert s.upload.max_size_mb > 0


@unit
def test_app_meta():
    """app_name 与 version 非空."""
    s = get_settings()
    assert s.app_name
    assert s.version