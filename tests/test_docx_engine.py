"""
Tests for the DOCX Engine.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.engines.docx.engine import DOCXEngine
from src.core.exceptions import TemplateNotFoundError
from src.core.parser.preprocessor import InputPreprocessor
from src.core.planner.content_planner import ContentPlanner

TEMPLATE_PATH = Path(__file__).parent / "templates" / "sample-ebook.docx"
SUMMARY_MD = Path(__file__).parent / "data" / "sample-summary.md"


@pytest.fixture
def engine():
    return DOCXEngine()


@pytest.fixture
def doc_plan():
    if not SUMMARY_MD.exists():
        pytest.skip("Test data not available")
    parsed = InputPreprocessor().parse(SUMMARY_MD)
    return ContentPlanner.plan_document(parsed)


def test_missing_template_raises_error(engine, doc_plan, tmp_path):
    with pytest.raises(TemplateNotFoundError):
        engine.render(doc_plan, tmp_path / "ghost.docx", tmp_path / "out.docx")


def test_render_produces_output_file(engine, doc_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.docx"
    result = engine.render(doc_plan, TEMPLATE_PATH, out)
    assert result.exists()


def test_output_is_valid_docx(engine, doc_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.docx"
    engine.render(doc_plan, TEMPLATE_PATH, out)
    from docx import Document
    doc = Document(str(out))
    assert len(doc.paragraphs) > 0


def test_output_has_content(engine, doc_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.docx"
    engine.render(doc_plan, TEMPLATE_PATH, out)
    from docx import Document
    doc = Document(str(out))
    all_text = " ".join(p.text for p in doc.paragraphs if p.text.strip())
    assert len(all_text) > 100


def test_no_markdown_artifacts_in_output(engine, doc_plan, tmp_path):
    if not TEMPLATE_PATH.exists():
        pytest.skip("Template not available")
    out = tmp_path / "output.docx"
    engine.render(doc_plan, TEMPLATE_PATH, out)
    from docx import Document
    doc = Document(str(out))
    for para in doc.paragraphs:
        for run in para.runs:
            for artifact in ["***", "**", "__"]:
                assert artifact not in run.text, (
                    f"Artifact '{artifact}' found in: '{run.text[:60]}'"
                )


def test_render_without_template_uses_inline(engine, tmp_path):
    """DOCX engine should still produce output from a plain md file even without template."""
    f = tmp_path / "simple.md"
    f.write_text(
        "# Simple Doc\n\n## Section\n\nHello world.\n\n- Item 1\n- Item 2\n",
        encoding="utf-8",
    )
    parsed = InputPreprocessor().parse(f)
    plan = ContentPlanner.plan_document(parsed)

    # Create a minimal blank template
    from docx import Document as DocxDoc
    blank = DocxDoc()
    template_path = tmp_path / "blank.docx"
    blank.save(str(template_path))

    out = tmp_path / "output.docx"
    engine.render(plan, template_path, out)
    assert out.exists()
    doc = DocxDoc(str(out))
    all_text = " ".join(p.text for p in doc.paragraphs if p.text.strip())
    assert "Hello world" in all_text
