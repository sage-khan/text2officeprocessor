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


def test_html_headings_become_sections(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body>"
        "<h1>Main Title</h1>"
        "<h2>Chapter One</h2><p>First paragraph.</p>"
        "<h2>Chapter Two</h2><p>Second paragraph.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    assert doc.title == "Main Title"
    assert len(doc.sections) == 2
    assert doc.sections[0].title == "Chapter One"
    assert doc.sections[1].title == "Chapter Two"


def test_html_list_parsed(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body><h2>Items</h2>"
        "<ul><li>Alpha</li><li>Beta</li><li>Gamma</li></ul>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    lists = [b for s in doc.sections for b in s.content if b.content_type.value == "list"]
    assert len(lists) == 1
    assert lists[0].data == ["Alpha", "Beta", "Gamma"]


def test_html_table_parsed(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body><h2>Data</h2>"
        "<table><thead><tr><th>Name</th><th>Score</th></tr></thead>"
        "<tbody><tr><td>Alice</td><td>95</td></tr>"
        "<tr><td>Bob</td><td>87</td></tr></tbody></table>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    tables = [b for s in doc.sections for b in s.content if b.content_type.value == "table"]
    assert len(tables) == 1
    assert tables[0].data["headers"] == ["Name", "Score"]
    assert tables[0].data["rows"][0] == ["Alice", "95"]


def test_html_inline_formatting_stripped(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body><h2>Styled</h2>"
        "<p>This is <strong>bold</strong> and <em>italic</em> text.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    paras = [b for s in doc.sections for b in s.content if b.content_type.value == "paragraph"]
    assert len(paras) == 1
    assert "bold" in paras[0].data
    assert "italic" in paras[0].data


def test_html_image_parsed(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body><h2>Visuals</h2>"
        '<img src="chart.png" alt="Sales chart">'
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    images = [b for s in doc.sections for b in s.content if b.content_type.value == "image"]
    assert len(images) == 1
    assert images[0].data["path"] == "chart.png"
    assert images[0].data["alt"] == "Sales chart"


def test_html_script_style_ignored(preprocessor, tmp_path):
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><head><style>body{color:red}</style></head><body>"
        "<h2>Real Content</h2>"
        "<script>alert('xss')</script>"
        "<p>Visible paragraph.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = preprocessor.parse(f)
    all_text = " ".join(
        str(b.data) for s in doc.sections for b in s.content
    )
    assert "alert" not in all_text
    assert "color:red" not in all_text
    assert "Visible paragraph" in all_text


def test_sample_summary_parses(preprocessor):
    summary_path = Path(__file__).parent / "data" / "sample-summary.md"
    if not summary_path.exists():
        pytest.skip("Test data not available")
    doc = preprocessor.parse(summary_path)
    assert doc.title != ""
    assert len(doc.sections) > 0
