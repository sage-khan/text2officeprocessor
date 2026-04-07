"""
Tests for the ContentPlanner module.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.planner.content_planner import ContentPlanner
from src.core.models import SlideDefinition, SlidePlan


SLIDES_MD_PATH = Path(__file__).parent / "data" / "sample-slides.md"


def test_parse_slides_markdown_returns_slide_plan():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    assert isinstance(plan, SlidePlan)
    assert len(plan.slides) >= 1


def test_all_slides_have_template_index():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    for slide in plan.slides:
        assert isinstance(slide.template_index, int)
        assert slide.template_index >= 0


def test_section_header_slide_has_replacements():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    first_slide = plan.slides[0]
    assert first_slide.template_index >= 0
    assert len(first_slide.replacements) > 0


def test_bullet_slide_has_bullets():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    # Slide 3 (index 2) is the first multi-point slide
    bullet_slides = [s for s in plan.slides if s.bullets]
    assert len(bullet_slides) > 0
    assert len(bullet_slides[0].bullets) > 0


def test_key_highlights_slide_has_items():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    card_slides = [s for s in plan.slides if any(k.startswith("card_") for k in s.items)]
    assert len(card_slides) > 0
    assert "card_1_title" in card_slides[0].items


def test_excellence_grid_slide_has_items():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    grid_slides = [s for s in plan.slides if any(k.startswith("item_0") for k in s.items)]
    assert len(grid_slides) > 0


def test_multiline_placeholder_parsed():
    """Verify that multiline placeholder old-text is joined correctly."""
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    plan = ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)
    # Find any slide that has a replacement — multiline parsing should produce clean keys
    slides_with_replacements = [s for s in plan.slides if s.replacements]
    assert len(slides_with_replacements) > 0
    for slide in slides_with_replacements:
        for key in slide.replacements:
            assert key.strip() != ""


def test_spreadsheet_plan_from_markdown(tmp_path):
    """SpreadsheetPlan should create sheets from document sections."""
    from src.core.parser.preprocessor import InputPreprocessor
    from src.core.planner.content_planner import ContentPlanner

    f = tmp_path / "data.md"
    f.write_text(
        "# Report\n\n## Sales Data\n\n| Product | Revenue |\n|---------|--------|\n| A | 1000 |\n| B | 2000 |\n",
        encoding="utf-8",
    )
    parsed = InputPreprocessor().parse(f)
    plan = ContentPlanner.plan_spreadsheet(parsed)
    assert len(plan.sheets) > 0
    # Find the sheet that has the table data (may not be index 0)
    data_sheets = [s for s in plan.sheets if s.columns or s.rows]
    assert len(data_sheets) > 0
    sheet = data_sheets[0]
    assert "Product" in sheet.columns
    assert len(sheet.rows) == 2
