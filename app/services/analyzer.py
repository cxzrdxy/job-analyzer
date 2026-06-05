"""分析服务:组合解析/抽取/工作流,作为业务编排入口."""
from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator, Optional

from app.core.config import get_settings
from app.core.errors import AppError, ParseError, WorkflowError
from app.core.logging import get_logger
from app.parsers.text_extractor import extract_text
from app.workflow.graph import build_workflow
from app.workflow.progress import (
    STAGES,
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

    def analyze(
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

        resume_text = self._load_resume_text(resume_bytes, resume_path, resume_suffix)
        job_text_value = self._load_job_text(job_text, job_bytes, job_path, job_suffix)

        if not resume_text.strip():
            raise ParseError("简历内容为空,请检查文件是否包含可识别的文本")
        if not job_text_value.strip():
            raise ParseError("岗位 JD 内容为空")

        initial: AgentState = {
            "inputs": {
                "resume_text": resume_text,
                "job_text": job_text_value,
                "trace_id": trace_id,
            }
        }
        try:
            final = self._get_workflow().invoke(initial)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("工作流执行失败 trace_id=%s", trace_id)
            raise WorkflowError(f"工作流执行失败: {exc}") from exc

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

        核心策略:单次 workflow.astream() 调用,按节点事件映射到阶段进度.
        事件序列: meta → upload → (stage_start → stage_end)×N → done | error
        """
        trace_id = trace_id or str(uuid.uuid4())
        t0 = time.monotonic()

        # ---- 1. 校验 + 读文件(upload 阶段) ----
        upload_stage = stage_by_key("upload")
        assert upload_stage is not None
        yield _json_line(make_meta_event(trace_id))
        yield _json_line(make_stage_start_event(upload_stage))

        try:
            resume_text = self._load_resume_text(resume_bytes, resume_path, resume_suffix)
            job_text_value = self._load_job_text(job_text, job_bytes, job_path, job_suffix)

            if not resume_text.strip():
                raise ParseError("简历内容为空,请检查文件是否包含可识别的文本")
            if not job_text_value.strip():
                raise ParseError("岗位 JD 内容为空")
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

        # ---- 3. 单次 astream,按节点事件映射阶段 ----
        workflow = self._get_workflow()

        # 设置全局 progress_callback(ContextVar),LLMClient 构造时自动拾取
        set_progress_callback(self._make_progress_callback())

        final_state = None
        try:
            async for event in workflow.astream(initial):
                # event 格式: {node_name: state} 或 {"__end__": state}(旧版 langgraph)
                if "__end__" in event:
                    final_state = event["__end__"]
                    break

                # 取出当前触发的节点名
                node_name = next(iter(event.keys()), None)
                if node_name is None:
                    continue

                # 映射到阶段定义
                stage = stage_by_node(node_name)
                if stage is None:
                    logger.warning("astream 事件来自未知节点 %s,跳过", node_name)
                    # 仍然合并状态
                    for k, v in event[node_name].items():
                        initial[k] = v
                    continue

                # 设置当前阶段上下文(供回调计算 percent 使用)
                set_current_stage(stage)

                # 推送阶段开始
                yield _json_line(make_stage_start_event(stage))

                # 合并节点输出到状态
                node_output = event[node_name]
                for k, v in node_output.items():
                    initial[k] = v

                # 推送阶段结束
                yield _json_line(make_stage_end_event(stage))
            else:
                # langgraph 0.2.x 的 astream 不再发送 __end__ 事件;
                # 循环自然结束(无 break)说明 workflow 已跑完,此时累积的 `initial`
                # 即为最终 state。这是这次空结果 bug 的修复点。
                final_state = initial

        except AppError as exc:
            current = get_current_stage()
            yield _json_line(make_error_event(
                current.key if current else "unknown",
                exc.code,
                str(exc),
            ))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("工作流执行失败 trace_id=%s", trace_id)
            current = get_current_stage()
            yield _json_line(make_error_event(
                current.key if current else "unknown",
                "workflow_error",
                str(exc),
            ))
            return
        finally:
            # 清理上下文
            set_progress_callback(None)
            set_current_stage(None)

        # ---- 4. 组装结果,输出 done ----
        duration_ms = (time.monotonic() - t0) * 1000
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

    def _make_progress_callback(self):
        """创建全局 progress_callback.

        回调签名: (phase: str, info: dict) -> None
        phase ∈ {"first_token", "streaming", "error"}
        通过 ContextVar 获取当前阶段来计算 percent.
        """

        def callback(phase: str, info: dict) -> None:
            stage = get_current_stage()
            if stage is None:
                return
            logger.debug(
                "stage=%s phase=%s chars=%s",
                stage.key,
                phase,
                info.get("chars", 0),
            )
            # 注意:同步回调无法直接 yield NDJSON 行;
            # token 级进度推送需要 asyncio.Queue + 异步消费,
            # 第一版先做日志记录,前端通过 stage_start/end 感知进度.

        return callback

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
