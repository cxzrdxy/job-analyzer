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
        # 优先级:显式参数 > ContextVar > 线程安全共享变量 > None
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
            # LangGraph astream() 在线程池中执行同步节点,
            # ContextVar 不会传播到工作线程,回退到线程安全的共享变量
            if self._progress_callback is None:
                try:
                    from app.workflow.progress import get_progress_callback_shared

                    cb = get_progress_callback_shared()
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
        """调用 LLM 并按 schema 解析 JSON,失败时自动重试一次."""
        cb = progress_callback or self._progress_callback
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                content = self._invoke(system, user, hint=schema.__name__ if attempt == 0 else None, progress_callback=cb)
                payload = _safe_json_loads(content)
                return schema.model_validate(payload)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("LLM 输出解析失败(第 %s 次): %s", attempt + 1, exc)
                user = user + "\n\n请严格输出符合 JSON Schema 的结果,不要再追加解释。"
        raise ExtractError(f"LLM 输出始终无法解析为 {schema.__name__}: {last_error}")

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


def _safe_json_loads(content: str) -> Any:
    """容忍 LLM 把 JSON 包在 ```json ... ``` 代码块的情况."""
    text = content.strip()
    if text.startswith("```"):
        # 去掉首尾三反引号
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
