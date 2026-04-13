"""Tests for the content extraction module (Office → Markdown)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.extraction.content_extractor import extract_content

_TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "data" / "templates"
_DOCX_TEMPLATE = _TEMPLATE_DIR / "generic-document.docx"
_PPTX_TEMPLATE = _TEMPLATE_DIR / "generic-slides.pptx"


# ---------------------------------------------------------------------------
# Helpers — generate test Office files from known Markdown
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_md(tmp_path_factory) -> Path:
    """Create a test Markdown file with known content."""
    p = tmp_path_factory.mktemp("input") / "test.md"
    p.write_text(
        "# Test Document\n\n"
        "## Section One\n\n"
        "- Alpha\n"
        "- Beta\n"
        "- Gamma\n\n"
        "## Section Two\n\n"
        "Some paragraph text here.\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture(scope="module")
def generated_outputs(test_md, tmp_path_factory) -> dict[str, Path]:
    """Generate PPTX, DOCX, XLSX from test Markdown."""
    from src.core.parser.preprocessor import InputPreprocessor
    from src.core.llm.normalizer import LLMNormalizer
    from src.core.planner.content_planner import ContentPlanner
    from src.core.engines.pptx.engine import PPTXEngine
    from src.core.engines.docx.engine import DOCXEngine
    from src.core.engines.xlsx.engine import XLSXEngine

    out_dir = tmp_path_factory.mktemp("generated")

    parsed = InputPreprocessor().parse(test_md)
    normalized = LLMNormalizer(provider=None).normalize(parsed)

    pptx_path = out_dir / "test.pptx"
    plan = ContentPlanner().plan_slides(parsed, normalized)
    PPTXEngine().render(plan, _PPTX_TEMPLATE, pptx_path)

    docx_path = out_dir / "test.docx"
    doc_plan = ContentPlanner.plan_document(parsed)
    DOCXEngine().render(doc_plan, _DOCX_TEMPLATE, docx_path)

    xlsx_path = out_dir / "test.xlsx"
    xl_plan = ContentPlanner.plan_spreadsheet(parsed)
    from src.core.engines.xlsx.engine import XLSXEngine
    XLSXEngine().render(xl_plan, xlsx_path)

    return {"pptx": pptx_path, "docx": docx_path, "xlsx": xlsx_path}


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def test_extract_docx_produces_content_md(generated_outputs, tmp_path):
    out = tmp_path / "docx_out"
    path = extract_content(generated_outputs["docx"], out)
    assert path.exists()
    assert path.name == "content.md"
    text = path.read_text(encoding="utf-8")
    assert "Section One" in text
    assert "Alpha" in text


def test_extract_docx_produces_styles(generated_outputs, tmp_path):
    out = tmp_path / "docx_styles_out"
    extract_content(generated_outputs["docx"], out, extract_styles=True)
    assert (out / "styles.json").exists()


def test_extract_docx_no_styles(generated_outputs, tmp_path):
    out = tmp_path / "docx_nostyles"
    extract_content(generated_outputs["docx"], out, extract_styles=False)
    assert not (out / "styles.json").exists()


# ---------------------------------------------------------------------------
# PPTX extraction
# ---------------------------------------------------------------------------

def test_extract_pptx_produces_slides_md(generated_outputs, tmp_path):
    out = tmp_path / "pptx_out"
    path = extract_content(generated_outputs["pptx"], out)
    assert path.exists()
    assert path.name == "slides.md"
    text = path.read_text(encoding="utf-8")
    assert "## SLIDE" in text


def test_extract_pptx_contains_content(generated_outputs, tmp_path):
    out = tmp_path / "pptx_content"
    path = extract_content(generated_outputs["pptx"], out)
    text = path.read_text(encoding="utf-8")
    assert "Section One" in text


def test_extract_pptx_produces_styles(generated_outputs, tmp_path):
    out = tmp_path / "pptx_styles_out"
    extract_content(generated_outputs["pptx"], out, extract_styles=True)
    assert (out / "pptx_styles.json").exists()


# ---------------------------------------------------------------------------
# XLSX extraction
# ---------------------------------------------------------------------------

def test_extract_xlsx_produces_content_md(generated_outputs, tmp_path):
    out = tmp_path / "xlsx_out"
    path = extract_content(generated_outputs["xlsx"], out)
    assert path.exists()
    assert path.name == "content.md"
    text = path.read_text(encoding="utf-8")
    assert "Section One" in text or "Alpha" in text


def test_extract_xlsx_no_styles_json(generated_outputs, tmp_path):
    """XLSX does not produce a styles.json (unsupported for style extraction)."""
    out = tmp_path / "xlsx_nostyles"
    extract_content(generated_outputs["xlsx"], out, extract_styles=True)
    assert not (out / "styles.json").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_extract_unsupported_format(tmp_path):
    txt = tmp_path / "file.csv"
    txt.write_text("a,b,c")
    with pytest.raises(Exception, match="Unsupported format"):
        extract_content(txt, tmp_path / "out")


def test_extract_output_dir_created(generated_outputs, tmp_path):
    out = tmp_path / "nested" / "deep" / "dir"
    extract_content(generated_outputs["docx"], out)
    assert out.exists()
    assert (out / "content.md").exists()


# ---------------------------------------------------------------------------
# CLI integration (smoke tests)
# ---------------------------------------------------------------------------

def test_cli_extract_styles(generated_outputs, tmp_path):
    """Smoke test: extract-styles via CLI runner."""
    from typer.testing import CliRunner
    from src.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, [
        "extract-styles",
        str(generated_outputs["docx"]),
        "-o", str(tmp_path / "styles.json"),
    ])
    assert result.exit_code == 0
    assert "Extracted" in result.output


def test_cli_extract(generated_outputs, tmp_path):
    """Smoke test: extract via CLI runner."""
    from typer.testing import CliRunner
    from src.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, [
        "extract",
        str(generated_outputs["docx"]),
        "-o", str(tmp_path / "extracted"),
    ])
    assert result.exit_code == 0
    assert "Content" in result.output


def test_cli_analyze_template():
    """Smoke test: analyze-template via CLI runner."""
    from typer.testing import CliRunner
    from src.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, [
        "analyze-template",
        str(_PPTX_TEMPLATE),
    ])
    assert result.exit_code == 0
    assert "PPTX" in result.output
    assert "Slide layouts" in result.output


def test_cli_diff_styles_identical(generated_outputs, tmp_path):
    """diff-styles of a file against itself should report no differences."""
    from typer.testing import CliRunner
    from src.cli.main import app

    from src.core.extraction.style_extractor import extract_styles
    ss = extract_styles(generated_outputs["docx"])
    p = ss.save(tmp_path / "s.json")

    runner = CliRunner()
    result = runner.invoke(app, ["diff-styles", str(p), str(p)])
    assert result.exit_code == 0
    assert "No style differences" in result.output
