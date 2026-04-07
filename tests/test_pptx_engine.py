"""
Tests for the PPTX Engine.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.engines.pptx.engine import PPTXEngine, sanitize_presentation, set_bullets
from src.core.exceptions import TemplateNotFoundError, RenderError
from src.core.planner.content_planner import ContentPlanner

TEMPLATE_PATH = Path(__file__).parent / "templates" / "sample-sections.pptx"
SLIDES_MD_PATH = Path(__file__).parent / "data" / "sample-slides.md"
MIN_EXPECTED_SIZE = 500_000  # 500KB minimum for a real background-preserved output


@pytest.fixture
def engine():
    return PPTXEngine()


@pytest.fixture
def slide_plan():
    if not SLIDES_MD_PATH.exists():
        pytest.skip("Test data not available")
    return ContentPlanner.parse_slides_markdown(SLIDES_MD_PATH)


def test_missing_template_raises_error(engine, slide_plan, tmp_path):
    with pytest.raises(TemplateNotFoundError):
        engine.render(slide_plan, tmp_path / "ghost.pptx", tmp_path / "out.pptx")


def test_empty_plan_raises_error(engine, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    from src.core.models import SlidePlan
    empty_plan = SlidePlan(title="empty")
    with pytest.raises(RenderError, match="no slides"):
        engine.render(empty_plan, TEMPLATE_PATH, tmp_path / "out.pptx")


def test_render_produces_output_file(engine, slide_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    result = engine.render(slide_plan, TEMPLATE_PATH, out)
    assert result.exists()


def test_output_is_valid_pptx(engine, slide_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    engine.render(slide_plan, TEMPLATE_PATH, out)
    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == len(slide_plan.slides)


def test_output_preserves_backgrounds(engine, slide_plan, tmp_path):
    """File size heuristic: full backgrounds preserved means >500KB for 22 slides."""
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    engine.render(slide_plan, TEMPLATE_PATH, out)
    assert out.stat().st_size >= MIN_EXPECTED_SIZE, (
        f"Output file {out.stat().st_size} bytes is suspiciously small — "
        "backgrounds may not be preserved."
    )


def test_no_markdown_artifacts_in_output(engine, slide_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    engine.render(slide_plan, TEMPLATE_PATH, out)
    from pptx import Presentation
    prs = Presentation(str(out))
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        for artifact in ["***", "**", "__"]:
                            assert artifact not in run.text, (
                                f"Markdown artifact '{artifact}' found in slide text: '{run.text[:60]}'"
                            )


def test_section_header_title_replaced(engine, slide_plan, tmp_path):
    """First slide should have the section title, not the template placeholder."""
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    engine.render(slide_plan, TEMPLATE_PATH, out)
    from pptx import Presentation
    prs = Presentation(str(out))
    first_slide = prs.slides[0]
    all_text = " ".join(
        run.text
        for shape in first_slide.shapes
        if shape.has_text_frame
        for para in shape.text_frame.paragraphs
        for run in para.runs
        if run.text.strip()
    )
    # The template placeholder must no longer appear — replaced with actual content
    assert "Section Name Here" not in all_text


def test_validator_passes_on_good_output(engine, slide_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.pptx"
    engine.render(slide_plan, TEMPLATE_PATH, out)
    from src.core.validation.validator import ProgrammaticValidator
    result = ProgrammaticValidator().validate_pptx(out)
    assert result.passed
    errors = [i for i in result.issues if i.severity == "error"]
    assert len(errors) == 0
