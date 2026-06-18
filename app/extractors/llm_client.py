"""LLM 客户端封装.

- 基于 langchain 的 ChatModel,统一调用入口
- 通过 schema 约束输出,失败时回退重试
- 支持流式输出(model.stream) + progress_callback 钩子
- 不在解析器/节点里直接拼 prompt,集中在这里
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError

from app.core.config import LLMSettings, get_settings
from app.core.errors import ExtractError
from app.core.logging import get_logger

logger = get_logger(__name__)

# 回调签名: (phase: str, info: dict) -> None
# phase ∈ {"first_token", "streaming", "error"}
ProgressCallback = Optional[Callable[[str, dict[str, Any]], None]]

# 累计多少字符触发一次 streaming 回调(默认 80)
_STREAMING_CHARS_THRESHOLD = 80


class LLMClient:
    """轻量 LLM 客户端."""

    def __init__(
        self,
        settings: Optional[LLMSettings] = None,
        *,
        progress_callback: ProgressCallback = None,
    ) -> None:
        self.settings = settings or get_settings().llm
        self._model = None
        # 始终初始化,避免 chat_json / chat_text / _invoke 在无 callback 时 AttributeError
        self._progress_callback: ProgressCallback = None
        # 优先级:显式参数 > 线程安全共享变量 > None
        if progress_callback is not None:
            self._progress_callback = progress_callback
        else:
            try:
                from app.workflow.progress import get_progress_callback

                cb = get_progress_callback()
                if cb is not None:
                    self._progress_callback = cb
            except Exception:
                pass

    def _get_model(self):  # noqa: ANN202 - 动态类型
        if self._model is not None:
            return self._model
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ExtractError("缺少 langchain-openai,请先安装依赖") from exc

        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "timeout": self.settings.timeout,
        }
        if self.settings.api_key:
            kwargs["api_key"] = self.settings.api_key
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url

        self._model = ChatOpenAI(**kwargs)
        return self._model

    # ---- 公开接口 ----

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Type[BaseModel],
        *,
        max_retries: int = 1,
        progress_callback: ProgressCallback = None,
    ) -> BaseModel:
        """调用 LLM 并按 schema 解析 JSON,失败时自动重试."""
        cb = progress_callback or self._progress_callback
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                content = self._invoke(system, user, hint=schema.__name__ if attempt == 0 else None, progress_callback=cb)
                payload = _safe_json_loads(content)
                # LLM 经常直接输出 list 而非包裹在 dict 中，自动修正
                payload = _coerce_payload(payload, schema)
                return schema.model_validate(payload)
            except ExtractError as exc:
                last_error = exc
                logger.warning("LLM 调用失败(第 %s 次): %s", attempt + 1, exc)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("LLM 输出解析失败(第 %s 次): %s", attempt + 1, exc)
                user = user + "\n\n请严格输出符合 JSON Schema 的结果,不要再追加解释。"
        raise ExtractError(f"LLM 调用始终失败({schema.__name__}): {last_error}")

    def chat_text(
        self,
        system: str,
        user: str,
        *,
        progress_callback: ProgressCallback = None,
    ) -> str:
        cb = progress_callback or self._progress_callback
        return self._invoke(system, user, hint=None, progress_callback=cb)

    # ---- 内部调用 ----

    def _invoke(
        self,
        system: str,
        user: str,
        hint: Optional[str],
        *,
        progress_callback: ProgressCallback = None,
    ) -> str:
        """核心调用:有 callback 时走 stream,否则走 invoke(向后兼容)."""
        cb = progress_callback or self._progress_callback
        if cb is not None:
            return self._invoke_stream(system, user, hint, cb)
        return _invoke_sync(self._get_model(), system, user, hint)

    def _invoke_stream(
        self,
        system: str,
        user: str,
        hint: Optional[str],
        callback: Callable[[str, dict[str, Any]], None],
    ) -> str:
        """流式调用 LLM,通过 callback 推送 token 级进度."""
        from langchain_core.messages import HumanMessage, SystemMessage

        model = self._get_model()
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        content_parts: list[str] = []
        total_chars = 0
        has_first_token = False

        try:
            for chunk in model.stream(messages):
                chunk_text = getattr(chunk, "content", "")
                if isinstance(chunk_text, list):
                    chunk_text = "\n".join(str(p) for p in chunk_text)
                if not chunk_text:
                    continue

                content_parts.append(chunk_text)
                total_chars += len(chunk_text)

                if not has_first_token:
                    has_first_token = True
                    callback("first_token", {"chars": total_chars})

                elif total_chars % _STREAMING_CHARS_THRESHOLD < len(chunk_text):
                    callback("streaming", {"chars": total_chars})

        except Exception as exc:  # noqa: BLE001
            callback("error", {"error": str(exc)})
            raise ExtractError(f"LLM 调用失败: {exc}") from exc

        full_content = "".join(content_parts)
        if hint and "{" not in full_content:
            logger.debug("LLM 返回内容未包含 JSON 片段,内容前 200 字: %s", full_content[:200])
        return full_content


def _invoke_sync(model, system: str, user: str, hint: Optional[str]) -> str:
    """同步 invoke 路径(无 callback 时使用,保持原有行为不变)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    try:
        response = model.invoke(messages)
    except Exception as exc:  # noqa: BLE001
        raise ExtractError(f"LLM 调用失败: {exc}") from exc

    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "\n".join(str(part) for part in content)
    if hint and "{" not in content:
        logger.debug("LLM 返回内容未包含 JSON 片段,内容前 200 字: %s", content[:200])
    return str(content)


def _coerce_payload(payload: Any, schema: Type[BaseModel]) -> Any:
    """修正 LLM 输出的常见结构偏差.

    典型问题:
    - LLM 直接输出 list,但 schema 期望 dict 包裹(如 SuggestionListOutput)
    - LLM 输出的子对象缺少必填字段,尝试用默认值补全
    """
    # 1. list → dict 包裹: 找到 schema 中唯一的 List 字段,把 list 包进去
    if isinstance(payload, list):
        for field_name, field_info in schema.model_fields.items():
            annotation = field_info.annotation
            # 解析 Optional / List[X] 等类型,找到 List 类字段
            origin = getattr(annotation, "__origin__", None)
            if origin is list or origin is List:
                logger.info("LLM 输出为 list,自动包裹为 {%s: [...]}", field_name)
                return {field_name: payload}
        # 没找到 List 字段,原样返回
        return payload

    # 2. dict 中子对象缺少必填字段: 尝试用默认值补全
    if isinstance(payload, dict):
        payload = _fill_missing_fields(payload, schema)

    return payload


def _fill_missing_fields(data: dict, schema: Type[BaseModel]) -> dict:
    """递归补全 LLM 输出中缺失的必填字段(用默认值或 None),并修正 Enum 值."""
    import enum as _enum

    result = dict(data)
    for field_name, field_info in schema.model_fields.items():
        if field_name not in result:
            # 有默认值的字段自动补全
            if field_info.default is not None and not isinstance(field_info.default, type):
                result[field_name] = field_info.default
            elif field_info.default_factory is not None:
                result[field_name] = field_info.default_factory()
            else:
                # 无默认值的必填字段,设为 None 让 Pydantic 报更清晰的错误
                result[field_name] = None
        elif isinstance(result[field_name], dict):
            # 递归处理嵌套模型
            sub_type = field_info.annotation
            # 解析 Optional[Model] 等
            args = getattr(sub_type, "__args__", None)
            if args:
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        sub_type = arg
                        break
            if isinstance(sub_type, type) and issubclass(sub_type, BaseModel):
                result[field_name] = _fill_missing_fields(result[field_name], sub_type)
        elif isinstance(result[field_name], list):
            # 处理列表中的嵌套模型
            sub_type = field_info.annotation
            args = getattr(sub_type, "__args__", None)
            item_type = args[0] if args else None
            if item_type and isinstance(item_type, type) and issubclass(item_type, BaseModel):
                new_list = []
                for item in result[field_name]:
                    if isinstance(item, dict):
                        new_list.append(_fill_missing_fields(item, item_type))
                    else:
                        new_list.append(item)
                result[field_name] = new_list

        # 修正 Enum 字段: LLM 经常输出不在枚举范围内的值
        value = result.get(field_name)
        if isinstance(value, str):
            ann = field_info.annotation
            # 解析 Optional[Enum] 等
            args = getattr(ann, "__args__", None)
            enum_type = None
            if args:
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, _enum.Enum):
                        enum_type = arg
                        break
            elif isinstance(ann, type) and issubclass(ann, _enum.Enum):
                enum_type = ann

            if enum_type is not None:
                # 尝试精确匹配
                valid_values = {e.value for e in enum_type}
                if value not in valid_values:
                    # 模糊匹配: 小写后包含关系
                    value_lower = value.lower()
                    matched = None
                    for e in enum_type:
                        if e.value in value_lower or value_lower in e.value:
                            matched = e.value
                            break
                    result[field_name] = matched if matched else list(valid_values)[0]

    return result


def _safe_json_loads(content: str) -> Any:
    """从 LLM 输出中提取并解析 JSON.

    容忍以下情况:
    - 纯 JSON
    - 整体被 ```json ... ``` 包裹
    - JSON 前后有解释文字
    - JSON 嵌在文本中间
    """
    import re

    text = content.strip()

    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 去掉 ```json ... ``` 代码块后再试
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. 从文本中提取 JSON: 按 { 和 [ 出现的先后顺序尝试
    brace_start = text.find("{")
    bracket_start = text.find("[")

    # 按出现顺序决定尝试顺序
    candidates = []
    if brace_start != -1:
        candidates.append(("brace", brace_start))
    if bracket_start != -1:
        candidates.append(("bracket", bracket_start))
    candidates.sort(key=lambda x: x[1])

    for kind, start_pos in candidates:
        if kind == "brace":
            # 提取 {...}
            depth = 0
            for i in range(start_pos, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_pos : i + 1]
                        try:
                            return json.loads(candidate)
                        except (json.JSONDecodeError, ValueError):
                            break
        else:
            # 提取 [...]
            depth = 0
            for i in range(start_pos, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_pos : i + 1]
                        try:
                            return json.loads(candidate)
                        except (json.JSONDecodeError, ValueError):
                            break

    # 全部失败，记录原始内容便于排查
    logger.warning(
        "LLM 输出无法解析为 JSON,原始内容(前 500 字): %s",
        text[:500],
    )
    return json.loads(text)
