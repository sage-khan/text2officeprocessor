"""Tests for the style extraction module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.extraction.models import (
    DocxStyle,
    ExtractedStyleSheet,
    FontProperties,
    ParagraphFormat,
    PlaceholderInfo,
    PptxSlideLayout,
    ThemeInfo,
)
from src.core.extraction.style_extractor import (
    extract_docx_styles,
    extract_pptx_styles,
    extract_styles,
)

_TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "data" / "templates"
_DOCX_TEMPLATE = _TEMPLATE_DIR / "generic-document.docx"
_PPTX_TEMPLATE = _TEMPLATE_DIR / "generic-slides.pptx"


# ---------------------------------------------------------------------------
# Auto-detect dispatcher
# ---------------------------------------------------------------------------

def test_extract_styles_auto_docx():
    ss = extract_styles(_DOCX_TEMPLATE)
    assert ss.format == "docx"
    assert len(ss.styles) > 0


def test_extract_styles_auto_pptx():
    ss = extract_styles(_PPTX_TEMPLATE)
    assert ss.format == "pptx"
    assert len(ss.slide_layouts) > 0


def test_extract_styles_unsupported_format(tmp_path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello")
    with pytest.raises(Exception, match="Unsupported template format"):
        extract_styles(txt)


def test_extract_styles_missing_file():
    with pytest.raises(Exception, match="not found"):
        extract_styles(Path("/tmp/nonexistent.docx"))


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def test_docx_styles_count():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    assert len(ss.styles) >= 10
    assert ss.format == "docx"


def test_docx_has_normal_style():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    names = {s.name for s in ss.styles}
    assert "Normal" in names


def test_docx_normal_font_properties():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    normal = next(s for s in ss.styles if s.name == "Normal")
    assert normal.font is not None
    assert normal.font.name == "Calibri"
    assert normal.font.size_pt == 11.0


def test_docx_heading_bold():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    h1 = next((s for s in ss.styles if s.style_id == "Heading1"), None)
    assert h1 is not None
    assert h1.font is not None
    assert h1.font.bold is True


def test_docx_numbering_defs():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    assert len(ss.numbering_defs) > 0


def test_docx_section_properties():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    assert ss.section_properties is not None
    assert ss.section_properties.page_width_pt > 0
    assert ss.section_properties.page_height_pt > 0


def test_docx_theme():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    assert ss.theme.major_font is not None
    assert len(ss.theme.colors) > 0


# ---------------------------------------------------------------------------
# PPTX extraction
# ---------------------------------------------------------------------------

def test_pptx_slide_count():
    ss = extract_pptx_styles(_PPTX_TEMPLATE)
    assert len(ss.slide_layouts) == 13


def test_pptx_slide_dimensions():
    ss = extract_pptx_styles(_PPTX_TEMPLATE)
    assert ss.slide_width_emu > 0
    assert ss.slide_height_emu > 0


def test_pptx_placeholders_present():
    ss = extract_pptx_styles(_PPTX_TEMPLATE)
    total_shapes = sum(len(l.placeholders) for l in ss.slide_layouts)
    assert total_shapes > 10


def test_pptx_theme():
    ss = extract_pptx_styles(_PPTX_TEMPLATE)
    assert ss.theme.major_font is not None or ss.theme.minor_font is not None
    assert len(ss.theme.colors) > 0


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

def test_stylesheet_to_json():
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    j = ss.to_json()
    data = json.loads(j)
    assert data["format"] == "docx"
    assert len(data["styles"]) > 0


def test_stylesheet_save_load(tmp_path):
    ss = extract_docx_styles(_DOCX_TEMPLATE)
    path = ss.save(tmp_path / "test_styles.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "md2office/v1"


def test_strip_none_omits_empty():
    ss = ExtractedStyleSheet(format="docx", source_file="test.docx")
    j = json.loads(ss.to_json())
    assert "styles" not in j  # empty list stripped
    assert "slide_layouts" not in j


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------

def test_placeholder_pt_conversion():
    ph = PlaceholderInfo(idx=0, type="title", left_emu=914400, top_emu=457200,
                         width_emu=9144000, height_emu=4572000)
    assert abs(ph.left_pt - 72.0) < 0.01
    assert abs(ph.top_pt - 36.0) < 0.01
    assert abs(ph.width_pt - 720.0) < 0.01


def test_font_properties_defaults():
    f = FontProperties()
    assert f.name is None
    assert f.bold is None
    assert f.size_pt is None


def test_timestamp_format():
    ts = ExtractedStyleSheet.timestamp()
    assert "T" in ts  # ISO format
    assert "+" in ts or "Z" in ts  # timezone
