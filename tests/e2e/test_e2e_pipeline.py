"""端到端抽取与匹配测试.

- 用真实 LLM 对 1 份后端简历 + 1 个后端 JD 跑完整流程
- 验证: parse_resume / parse_job / skill_gap / experience / keywords
        / aggregate / suggestions 全部产出符合 schema
- 失败阈值:技能匹配率、建议数量
"""
from __future__ import annotations

import asyncio

from tests.runner import e2e
from tests.fixtures.resumes import get_resumes_for_role
from tests.fixtures.jobs import get_jobs_by_category

from app.services.analyzer import AnalyzerService


@e2e
def test_e2e_backend_resume_vs_backend_jd():
    """一份后端简历 + 后端 JD 完整跑通."""
    resume = get_resumes_for_role("后端工程师")[0]
    job = get_jobs_by_category("互联网研发-后端")[0]

    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=resume.text.encode("utf-8"),
        resume_suffix=".txt",
        job_text=job.text,
        job_suffix=".txt",
        trace_id=f"e2e_{resume.id}_{job.id}",
    ))

    # 1. 顶层字段完整
    assert "trace_id" in result
    assert "match_report" in result
    assert "suggestions" in result
    assert result["match_report"] is not None

    mr = result["match_report"]
    assert "overall_score" in mr
    assert 0 <= mr["overall_score"] <= 100, f"score={mr['overall_score']}"

    # 2. skill_gap 三类齐全
    sg = mr["skill_gap"]
    assert "matched" in sg and "missing" in sg and "partial" in sg
    assert 0.0 <= sg["coverage"] <= 1.0

    # 3. 经验匹配
    ex = mr["experience"]
    assert "score" in ex
    assert 0.0 <= ex["score"] <= 1.0

    # 4. 关键词匹配
    kw = mr["keywords"]
    assert "matched" in kw and "missing" in kw
    assert 0.0 <= kw["coverage"] <= 1.0

    # 5. 建议数量 5-8 条(LLM 输出或 fallback)
    suggestions = result["suggestions"]
    assert len(suggestions) >= 1, "至少应有 fallback 建议"
    # LLM 路径下应为 5-8 条,fallback 路径下 3-5 条
    assert len(suggestions) <= 8, f"建议过多: {len(suggestions)}"

    # 6. 每条建议都包含关键字段
    for s in suggestions:
        for f in ("type", "priority", "section", "suggestion"):
            assert f in s, f"建议缺少字段 {f}: {s}"


@e2e
def test_e2e_frontend_resume_vs_frontend_jd():
    """前端简历 + 前端 JD."""
    resume = get_resumes_for_role("前端工程师")[0]
    job = get_jobs_by_category("互联网研发-前端")[0]

    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=resume.text.encode("utf-8"),
        resume_suffix=".txt",
        job_text=job.text,
        job_suffix=".txt",
        trace_id=f"e2e_{resume.id}_{job.id}",
    ))

    assert result["match_report"] is not None
    assert result["match_report"]["overall_score"] >= 0
    assert len(result["suggestions"]) >= 1


@e2e
def test_e2e_data_analyst_resume_vs_data_jd():
    """数据分析师简历 + 数据分析 JD."""
    resume = get_resumes_for_role("数据分析师")[0]
    job = get_jobs_by_category("数据/分析")[0]

    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=resume.text.encode("utf-8"),
        resume_suffix=".txt",
        job_text=job.text,
        job_suffix=".txt",
        trace_id=f"e2e_{resume.id}_{job.id}",
    ))

    assert result["match_report"] is not None
    # 数据分析师和数据分析 JD 同类,匹配分应较高
    score = result["match_report"]["overall_score"]
    assert score >= 30, f"同类匹配分不应过低,实际 {score}"


@e2e
def test_e2e_backend_resume_vs_finance_jd_low_score():
    """后端简历 + 金融 JD:跨行业,匹配分应明显较低."""
    resume = get_resumes_for_role("后端工程师")[0]
    job = get_jobs_by_category("传统行业-金融")[0]

    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=resume.text.encode("utf-8"),
        resume_suffix=".txt",
        job_text=job.text,
        job_suffix=".txt",
        trace_id=f"e2e_{resume.id}_{job.id}",
    ))

    assert result["match_report"] is not None
    score = result["match_report"]["overall_score"]
    # 跨行业匹配通常 < 50
    assert score < 60, f"跨行业匹配分应较低,实际 {score}"


@e2e
def test_e2e_stream_emits_events():
    """流式接口应当推送 NDJSON 事件."""
    import json

    resume = get_resumes_for_role("后端工程师")[0]
    job = get_jobs_by_category("互联网研发-后端")[0]

    service = AnalyzerService()

    async def collect():
        events = []
        async for line in service.analyze_stream(
            resume_bytes=resume.text.encode("utf-8"),
            resume_suffix=".txt",
            job_text=job.text,
            job_suffix=".txt",
            trace_id=f"e2e_stream_{resume.id}_{job.id}",
        ):
            events.append(json.loads(line))
        return events

    events = asyncio.run(collect())

    # 至少应当包含 meta, 多个 stage_*, done
    types = [e.get("type") for e in events]
    assert "meta" in types
    assert "done" in types
    assert any(t == "stage_start" for t in types)
    assert any(t == "stage_end" for t in types)

    # done 事件应当包含完整结果
    done = next(e for e in events if e.get("type") == "done")
    assert "data" in done
    assert "match_report" in done["data"]
    assert "suggestions" in done["data"]


@e2e
def test_e2e_suggestions_have_required_fields():
    """每条建议应当有可用的内容."""
    resume = get_resumes_for_role("后端工程师")[0]
    job = get_jobs_by_category("互联网研发-后端")[0]

    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=resume.text.encode("utf-8"),
        resume_suffix=".txt",
        job_text=job.text,
        job_suffix=".txt",
        trace_id=f"e2e_sug_{resume.id}_{job.id}",
    ))

    suggestions = result["suggestions"]
    assert suggestions, "至少应有 1 条建议"

    # 每条 suggestion 字段必须有实际内容
    for i, s in enumerate(suggestions):
        assert s.get("suggestion", "").strip(), f"第 {i} 条建议为空"
        assert s.get("priority") in ("high", "medium", "low"), \
            f"priority 非法: {s.get('priority')}"