"""
Tests for the InputPreprocessor module.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.parser.preprocessor import InputPreprocessor
from src.core.exceptions import InputFormatError
from src.core.models import ContentType


SAMPLE_MD = """# Test Document

## Section One

This is a paragraph of text.

- Bullet item one
- Bullet item two
- Bullet item three

## Section Two

Another paragraph here.

| Header A | Header B |
|----------|----------|
| Row 1A   | Row 1B   |
| Row 2A   | Row 2B   |
"""


@pytest.fixture
def preprocessor():
    return InputPreprocessor()


@pytest.fixture
def sample_md_file(tmp_path):
    f = tmp_path / "test.md"
    f.write_text(SAMPLE_MD, encoding="utf-8")
    return f


def test_parse_markdown_returns_parsed_document(preprocessor, sample_md_file):
    doc = preprocessor.parse(sample_md_file)
    assert doc.title == "Test Document"
    assert doc.source_format == "md"
    assert len(doc.sections) >= 2


def test_parse_extracts_list_blocks(preprocessor, sample_md_file):
    doc = preprocessor.parse(sample_md_file)
    list_blocks = [
        block for sec in doc.sections for block in sec.content
        if block.content_type == ContentType.LIST
    ]
    assert len(list_blocks) >= 1
    assert "Bullet item one" in list_blocks[0].data


def test_parse_extracts_table(preprocessor, sample_md_file):
    doc = preprocessor.parse(sample_md_file)
    table_blocks = [
        block for sec in doc.sections for block in sec.content
        if block.content_type == ContentType.TABLE
    ]
    assert len(table_blocks) >= 1
    assert table_blocks[0].data["headers"] == ["Header A", "Header B"]


def test_parse_extracts_paragraphs(preprocessor, sample_md_file):
    doc = preprocessor.parse(sample_md_file)
    para_blocks = [
        block for sec in doc.sections for block in sec.content
        if block.content_type == ContentType.PARAGRAPH
    ]
    assert len(para_blocks) >= 1


def test_missing_file_raises_error(preprocessor, tmp_path):
    with pytest.raises(InputFormatError, match="not found"):
        preprocessor.parse(tmp_path / "nonexistent.md")


def test_unsupported_format_raises_error(preprocessor, tmp_path):
    f = tmp_path / "test.pdf"
    f.write_text("content")
    with pytest.raises(InputFormatError, match="Unsupported format"):
        preprocessor.parse(f)


def test_txt_file_parsed(preprocessor, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("# Plain text doc\n\n## Section\n\nSome content here.\n", encoding="utf-8")
    doc = preprocessor.parse(f)
    assert doc.source_format == "txt"
    assert doc.title == "Plain text doc"


def test_markdown_artifacts_stripped(preprocessor, tmp_path):
    f = tmp_path / "artifact.md"
    f.write_text("# Doc\n\n## Sec\n\n**Bold text** and __underline__ here.\n", encoding="utf-8")
    doc = preprocessor.parse(f)
    para_texts = [
        str(b.data) for sec in doc.sections for b in sec.content
        if b.content_type == ContentType.PARAGRAPH
    ]
    for text in para_texts:
        assert "**" not in text
        assert "__" not in text


def test_sample_summary_parses(preprocessor):
    summary_path = Path(__file__).parent / "data" / "sample-summary.md"
    if not summary_path.exists():
        pytest.skip("Test data not available")
    doc = preprocessor.parse(summary_path)
    assert doc.title != ""
    assert len(doc.sections) > 0
