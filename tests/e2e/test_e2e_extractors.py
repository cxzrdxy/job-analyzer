"""解析器 E2E 测试.

- 把 .txt 简历与 JD 写入临时文件,走真实 extract_text 路径
- 验证 clean_text 后内容完整
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from tests.runner import e2e
from tests.fixtures.resumes import get_resumes_for_role
from tests.fixtures.jobs import get_jobs_by_category

from app.parsers.text_extractor import extract_text, extract_text_from_bytes


@e2e
def test_e2e_extract_txt_resume_file():
    """把简历文本写到 .txt 文件,再走 extract_text 路径."""
    resume = get_resumes_for_role("后端工程师")[0]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    ) as f:
        f.write(resume.text)
        path = f.name

    try:
        extracted = extract_text(path)
        assert "工作经历" in extracted
        assert "技能清单" in extracted
        assert "Python" in extracted
    finally:
        Path(path).unlink(missing_ok=True)


@e2e
def test_e2e_extract_txt_jd_file():
    """JD 文件提取."""
    job = get_jobs_by_category("互联网研发-后端")[0]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    ) as f:
        f.write(job.text)
        path = f.name

    try:
        extracted = extract_text(path)
        assert "岗位职责" in extracted
        assert "任职要求" in extracted
    finally:
        Path(path).unlink(missing_ok=True)


@e2e
def test_e2e_extract_from_bytes():
    """从字节流提取."""
    resume = get_resumes_for_role("前端工程师")[0]
    data = resume.text.encode("utf-8")
    extracted = extract_text_from_bytes(data, ".txt")
    assert "React" in extracted or "Vue" in extracted
    assert "工作经历" in extracted