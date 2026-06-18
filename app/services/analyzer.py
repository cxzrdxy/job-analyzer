"""分析服务:组合解析/抽取/工作流,作为业务编排入口."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Optional

from app.core.cache import safe_save_analysis
from app.core.config import get_settings
from app.core.errors import AppError, ParseError, WorkflowError
from app.core.logging import get_logger
from app.parsers.text_extractor import extract_text
from app.workflow.graph import build_workflow
from app.workflow.progress import (
    STAGES,
    compute_streaming_percent,
    get_current_stage,
    make_done_event,
    make_error_event,
    make_meta_event,
    make_progress_event,
    make_stage_end_event,
    make_stage_start_event,
    set_current_stage,
    set_progress_callback,
    stage_by_key,
    stage_by_node,
)
from app.workflow.state import AgentState

logger = get_logger(__name__)


def _json_line(obj: dict) -> bytes:
    """把 dict 编码为 NDJSON 行(以 \\n 结尾)."""
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def _dump_model(value: Any) -> Any:
    """把 Pydantic 模型转成 dict,其他值原样返回.

    缓存层需要的是可 JSON 序列化的字典;AgentState 中各字段既可能是 Pydantic
    模型,也可能是 dict(来自合并节点的部分输出),统一在此处理.
    """
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            return None
    return value


def _persist_cache(
    trace_id: str,
    final_state: Optional[dict],
) -> None:
    """分析完成后把中间结果写入缓存(异步后台任务).

    写入失败不影响主流程返回值(由 safe_save_analysis 内部降级).
    """
    if final_state is None:
        return
    resume_data = _dump_model(final_state.get("resume_data"))
    job_requirement = _dump_model(final_state.get("job_requirement"))
    match_report = _dump_model(final_state.get("match_report"))
    suggestions_raw = final_state.get("suggestions") or []
    # suggestions 在 state 中已经是 list[dict],但也可能混入 Pydantic 实例
    suggestions = [
        s.model_dump() if hasattr(s, "model_dump") else s
        for s in suggestions_raw
    ]

    meta = {
        "provider": get_settings().llm.provider,
        "model": get_settings().llm.model,
    }

    async def _do() -> None:
        await safe_save_analysis(
            trace_id,
            resume_data=resume_data,
            job_requirement=job_requirement,
            match_report=match_report,
            suggestions=suggestions,
            meta=meta,
        )

    # 后台写入,不阻塞主流程返回
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do())
    except RuntimeError:
        # 没有 running loop(同步调用入口),跳过缓存写入
        logger.debug("无 running loop,跳过缓存写入 trace_id=%s", trace_id)


class AnalyzerService:
    """对外暴露的统一分析服务.

    关键设计:
    - 先用本地解析器把上传文件转成纯文本
    - 再走 LangGraph 工作流完成结构化与分析
    - trace_id 贯穿全流程,便于排查
    - 流式接口(analyze_stream)通过 ContextVar 把 progress_callback 透传给 LLMClient
    """

    def __init__(self) -> None:
        self._workflow = None

    def _get_workflow(self):
        if self._workflow is None:
            self._workflow = build_workflow()
        return self._workflow

    async def analyze(
        self,
        *,
        resume_bytes: Optional[bytes] = None,
        resume_path: Optional[str] = None,
        resume_suffix: str = ".pdf",
        job_text: Optional[str] = None,
        job_bytes: Optional[bytes] = None,
        job_path: Optional[str] = None,
        job_suffix: str = ".txt",
        trace_id: Optional[str] = None,
    ) -> dict:
        trace_id = trace_id or str(uuid.uuid4())

        resume_text, job_text_value = self._prepare_input(
            resume_bytes=resume_bytes,
            resume_path=resume_path,
            resume_suffix=resume_suffix,
            job_text=job_text,
            job_bytes=job_bytes,
            job_path=job_path,
            job_suffix=job_suffix,
        )

        initial: AgentState = {
            "inputs": {
                "resume_text": resume_text,
                "job_text": job_text_value,
                "trace_id": trace_id,
            }
        }
        try:
            final = await self._get_workflow().ainvoke(initial)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("工作流执行失败 trace_id=%s", trace_id)
            raise WorkflowError(f"工作流执行失败: {exc}") from exc

        # 缓存中间结果(异步后台任务,失败不影响主流程返回)
        _persist_cache(trace_id, final)

        return {
            "trace_id": trace_id,
            "match_report": final.get("match_report").model_dump()
            if final.get("match_report") is not None
            else None,
            "suggestions": final.get("suggestions") or [],
            "meta": {
                "resume_chars": len(resume_text),
                "job_chars": len(job_text_value),
                "used_provider": get_settings().llm.provider,
                "used_model": get_settings().llm.model,
            },
        }

    async def analyze_stream(
        self,
        *,
        resume_bytes: Optional[bytes] = None,
        resume_path: Optional[str] = None,
        resume_suffix: str = ".pdf",
        job_text: Optional[str] = None,
        job_bytes: Optional[bytes] = None,
        job_path: Optional[str] = None,
        job_suffix: str = ".txt",
        trace_id: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """流式分析,逐行 yield NDJSON 事件.

        核心策略:
        - 工作流在后台 asyncio.Task 中运行,节点事件推入 asyncio.Queue
        - 进度回调通过 loop.call_soon_threadsafe 线程安全地推入同一队列
        - 主生成器从队列消费,实时 yield NDJSON 行(含 token 级进度)
        - 事件序列: meta → upload → (stage_start → progress… → stage_end)×N → done | error
        """
        trace_id = trace_id or str(uuid.uuid4())
        t0 = time.monotonic()

        # ---- 1. 校验 + 读文件(upload 阶段) ----
        upload_stage = stage_by_key("upload")
        assert upload_stage is not None
        yield _json_line(make_meta_event(trace_id))
        yield _json_line(make_stage_start_event(upload_stage))

        try:
            resume_text, job_text_value = self._prepare_input(
                resume_bytes=resume_bytes,
                resume_path=resume_path,
                resume_suffix=resume_suffix,
                job_text=job_text,
                job_bytes=job_bytes,
                job_path=job_path,
                job_suffix=job_suffix,
            )
        except AppError as exc:
            yield _json_line(make_error_event("upload", exc.code, str(exc)))
            return
        except Exception as exc:  # noqa: BLE001
            yield _json_line(make_error_event("upload", "unknown", str(exc)))
            return

        yield _json_line(make_stage_end_event(upload_stage))

        # ---- 2. 构建初始状态 ----
        initial: AgentState = {
            "inputs": {
                "resume_text": resume_text,
                "job_text": job_text_value,
                "trace_id": trace_id,
            }
        }

        # ---- 3. 队列 + 后台任务:实时推送进度 ----
        workflow = self._get_workflow()
        queue: asyncio.Queue[tuple] = asyncio.Queue(maxsize=200)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # 进度回调:在工作线程中被 LLMClient 调用,线程安全地推入队列
        def progress_callback(phase: str, info: dict) -> None:
            if loop is None:
                return
            stage = get_current_stage()
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    ("progress", phase, info, stage.key if stage else None),
                )
            except (RuntimeError, asyncio.QueueFull):
                pass

        set_progress_callback(progress_callback)

        # 后台任务:运行工作流,将节点事件推入队列
        async def run_workflow() -> None:
            try:
                async for event in workflow.astream(initial):
                    await queue.put(("node", event))
            except AppError as exc:
                await queue.put(("app_error", exc))
            except Exception as exc:  # noqa: BLE001
                await queue.put(("exception", exc))
            finally:
                await queue.put(("workflow_done", None))

        task = asyncio.create_task(run_workflow())

        final_state = None
        # 已推送 stage_start 的阶段集合,用于在首次收到进度时提前推送 stage_start
        started_stages: set[str] = set()

        try:
            while True:
                item = await queue.get()
                kind = item[0]

                # ---- 进度事件(LLM token 级) ----
                if kind == "progress":
                    _, phase, info, stage_key = item
                    if not stage_key:
                        continue
                    stage = stage_by_key(stage_key)
                    if not stage:
                        continue
                    # 首次收到该阶段的进度,先推送 stage_start
                    if stage_key not in started_stages:
                        started_stages.add(stage_key)
                        yield _json_line(make_stage_start_event(stage))
                    percent = compute_streaming_percent(stage, phase, info.get("chars", 0))
                    chars = info.get("chars", 0)
                    msg = f"已处理 {chars} 字符" if chars else ""
                    yield _json_line(make_progress_event(stage, percent, message=msg, chars=chars))

                # ---- 节点完成事件 ----
                elif kind == "node":
                    _, event = item
                    if "__end__" in event:
                        final_state = event["__end__"]
                        break

                    node_name = next(iter(event.keys()), None)
                    if node_name is None:
                        continue

                    stage = stage_by_node(node_name)
                    if stage is None:
                        logger.warning("astream 事件来自未知节点 %s,跳过", node_name)
                        for k, v in event[node_name].items():
                            initial[k] = v
                        continue

                    # 如果进度回调还没触发 stage_start,在这里补发
                    if stage.key not in started_stages:
                        started_stages.add(stage.key)
                        yield _json_line(make_stage_start_event(stage))

                    set_current_stage(stage)

                    # 合并节点输出到状态
                    node_output = event[node_name]
                    for k, v in node_output.items():
                        initial[k] = v

                    yield _json_line(make_stage_end_event(stage))

                # ---- 工作流异常 ----
                elif kind == "app_error":
                    _, exc = item
                    current = get_current_stage()
                    yield _json_line(make_error_event(
                        current.key if current else "unknown",
                        exc.code,
                        str(exc),
                    ))
                    return

                elif kind == "exception":
                    _, exc = item
                    logger.exception("工作流执行失败 trace_id=%s", trace_id)
                    current = get_current_stage()
                    yield _json_line(make_error_event(
                        current.key if current else "unknown",
                        "workflow_error",
                        str(exc),
                    ))
                    return

                # ---- 工作流完成(langgraph 0.2.x 不发 __end__) ----
                elif kind == "workflow_done":
                    final_state = initial
                    break

        finally:
            # 清理所有上下文
            set_progress_callback(None)
            set_current_stage(None)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # ---- 4. 组装结果,输出 done ----
        duration_ms = (time.monotonic() - t0) * 1000

        # 缓存中间结果(异步后台任务,失败不影响流式返回)
        _persist_cache(trace_id, final_state)

        result_data = {
            "trace_id": trace_id,
            "match_report": final_state.get("match_report").model_dump()
            if final_state and final_state.get("match_report") is not None
            else None,
            "suggestions": final_state.get("suggestions") or [] if final_state else [],
            "meta": {
                "resume_chars": len(resume_text),
                "job_chars": len(job_text_value),
                "used_provider": get_settings().llm.provider,
                "used_model": get_settings().llm.model,
            },
        }
        yield _json_line(make_done_event(result_data, duration_ms))

    # ---- 内部辅助 ----

    def _prepare_input(
        self,
        *,
        resume_bytes: Optional[bytes] = None,
        resume_path: Optional[str] = None,
        resume_suffix: str = ".pdf",
        job_text: Optional[str] = None,
        job_bytes: Optional[bytes] = None,
        job_path: Optional[str] = None,
        job_suffix: str = ".txt",
    ) -> tuple[str, str]:
        """读取并校验简历和 JD 文本,返回 (resume_text, job_text)."""
        resume_text = self._load_resume_text(resume_bytes, resume_path, resume_suffix)
        job_text_value = self._load_job_text(job_text, job_bytes, job_path, job_suffix)

        if not resume_text.strip():
            raise ParseError("简历内容为空,请检查文件是否包含可识别的文本")
        if not job_text_value.strip():
            raise ParseError("岗位 JD 内容为空")

        return resume_text, job_text_value

    def _load_resume_text(self, data: Optional[bytes], path: Optional[str], suffix: str) -> str:
        if data is not None:
            from app.parsers.text_extractor import extract_text_from_bytes

            return extract_text_from_bytes(data, suffix)
        if path:
            return extract_text(path)
        return ""

    def _load_job_text(
        self,
        text: Optional[str],
        data: Optional[bytes],
        path: Optional[str],
        suffix: str,
    ) -> str:
        if text and text.strip():
            return text
        if data is not None:
            from app.parsers.text_extractor import extract_text_from_bytes

            return extract_text_from_bytes(data, suffix)
        if path:
            return extract_text(path)
        return ""
