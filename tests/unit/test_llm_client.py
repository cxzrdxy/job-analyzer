"""LLM 客户端单元测试.

- LLMClient.chat_json: 真实 LLM 路径覆盖(由 e2e 负责)
- LLMClient.coerce_payload / fill_missing_fields: 纯函数,单元测试覆盖
- _safe_json_loads: 边界输入
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tests.runner import unit
from app.extractors.llm_client import (
    _coerce_payload,
    _fill_missing_fields,
    _safe_json_loads,
)
from app.models.suggestion import SuggestionListOutput, ResumeSuggestion


@unit
def test_safe_json_loads_plain():
    """普通 JSON 字符串."""
    assert _safe_json_loads('{"a": 1}') == {"a": 1}


@unit
def test_safe_json_loads_with_markdown_fence():
    """带 ```json 包裹的输出."""
    text = '下面是结果:\n```json\n{"x": [1,2,3]}\n```\n结束'
    assert _safe_json_loads(text) == {"x": [1, 2, 3]}


@unit
def test_safe_json_loads_with_brace_extraction():
    """JSON 嵌在文本中间."""
    text = "前面文字\n  {\"k\": \"v\"}  \n后面文字"
    assert _safe_json_loads(text) == {"k": "v"}


@unit
def test_safe_json_loads_list_extraction():
    """JSON 是 list 的情况."""
    text = "[1, 2, 3]"
    assert _safe_json_loads(text) == [1, 2, 3]


@unit
def test_safe_json_loads_invalid_raises():
    """完全无效的输入应当抛 JSONDecodeError."""
    import json
    try:
        _safe_json_loads("this is not json at all")
    except json.JSONDecodeError:
        return
    raise AssertionError("应当抛 JSONDecodeError")


@unit
def test_coerce_payload_list_to_dict():
    """LLM 直接输出 list 时,自动包裹到 schema 的 list 字段."""
    payload: Any = [{"type": "content", "suggestion": "a"}, {"type": "keyword", "suggestion": "b"}]
    result = _coerce_payload(payload, SuggestionListOutput)
    assert isinstance(result, dict)
    assert "suggestions" in result
    assert len(result["suggestions"]) == 2


@unit
def test_fill_missing_fields_defaults():
    """嵌套模型缺失字段应被默认值填充."""
    class Sub(BaseModel):
        a: int = 0
        b: str = "default"

    class Top(BaseModel):
        sub: Sub
        name: str = "x"

    data = {"sub": {}}   # sub 已存在但内容为空,递归填充 Sub 的默认值
    filled = _fill_missing_fields(data, Top)
    assert filled["sub"] == {"a": 0, "b": "default"}
    assert filled["name"] == "x"


@unit
def test_fill_missing_fields_enum_correction():
    """非法 Enum 值应被纠正到有效值."""
    from app.models.suggestion import SuggestionType, SuggestionPriority, ResumeSection

    payload = {
        "suggestions": [
            {"type": "content-like", "priority": "highh", "section": "sklls", "suggestion": "x"}
        ]
    }
    filled = _fill_missing_fields(payload, SuggestionListOutput)
    s = filled["suggestions"][0]
    assert s["type"] in {e.value for e in SuggestionType}
    assert s["priority"] in {e.value for e in SuggestionPriority}
    assert s["section"] in {e.value for e in ResumeSection}


@unit
def test_suggestion_list_output_min_max():
    """schema 限制 5-8 条建议."""
    # 通过 pydantic 直接验证:少于 5 条应当失败
    from pydantic import ValidationError

    try:
        SuggestionListOutput(suggestions=[
            ResumeSuggestion(suggestion=f"s{i}") for i in range(3)
        ])
    except ValidationError:
        return
    raise AssertionError("少于 5 条应触发 ValidationError")


@unit
def test_suggestion_list_output_max_constraint():
    """多于 8 条应当失败."""
    from pydantic import ValidationError

    try:
        SuggestionListOutput(suggestions=[
            ResumeSuggestion(suggestion=f"s{i}") for i in range(9)
        ])
    except ValidationError:
        return
    raise AssertionError("多于 8 条应触发 ValidationError")