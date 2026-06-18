"""解析器单元测试."""
from __future__ import annotations

from tests.runner import unit
from app.parsers.text_extractor import (
    DocxTextExtractor,
    PdfTextExtractor,
    TxtTextExtractor,
    clean_text,
    extract_text_from_bytes,
)


@unit
def test_clean_text_normalize_whitespace():
    """清洗应当合并连续空白字符."""
    raw = "hello\u00A0world\t!\n\n\n\nfoo"
    cleaned = clean_text(raw)
    assert "\u00A0" not in cleaned, "应当去除 NBSP"
    assert "\t" not in cleaned, "应当去除 tab"
    assert "\n\n\n" not in cleaned, "应当压缩 3+ 换行"
    assert "hello world" in cleaned


@unit
def test_clean_text_empty():
    """空输入应返回空串."""
    assert clean_text("") == ""
    assert clean_text(None) == ""


@unit
def test_txt_extractor_bytes():
    """TXT 字节流应被正确解码."""
    text = "测试中文内容\nLine2\nLine3"
    data = text.encode("utf-8")
    out = extract_text_from_bytes(data, ".txt")
    assert "测试中文内容" in out
    assert "Line2" in out


@unit
def test_txt_extractor_supports():
    """TXT 提取器后缀判断."""
    ext = TxtTextExtractor()
    assert ext.supports(".txt") is True
    assert ext.supports(".md") is True
    assert ext.supports(".pdf") is False


@unit
def test_pdf_extractor_supports():
    """PDF 提取器后缀判断."""
    ext = PdfTextExtractor()
    assert ext.supports(".PDF") is True   # 不区分大小写
    assert ext.supports(".txt") is False


@unit
def test_docx_extractor_supports():
    """DOCX 提取器后缀判断."""
    ext = DocxTextExtractor()
    assert ext.supports(".docx") is True
    assert ext.supports(".DOCX") is True
    assert ext.supports(".doc") is False


@unit
def test_extract_text_from_bytes_unsupported():
    """不支持的扩展名应抛 UnsupportedFileTypeError."""
    from app.core.errors import UnsupportedFileTypeError

    try:
        extract_text_from_bytes(b"dummy", ".xlsx")
    except UnsupportedFileTypeError:
        return
    raise AssertionError("期望 UnsupportedFileTypeError 未抛")