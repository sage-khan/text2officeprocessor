"""
Tests for the batch CLI command.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()

SAMPLE_MD_CONTENT = """\
# Batch Test Document

## Section One

This is the first paragraph of section one.

- Item alpha
- Item beta
- Item gamma

## Section Two

This is the second section with more content.

| Column A | Column B |
|----------|----------|
| Value 1  | Value 2  |
"""


@pytest.fixture
def input_dir(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    (d / "doc1.md").write_text(SAMPLE_MD_CONTENT, encoding="utf-8")
    (d / "doc2.md").write_text(SAMPLE_MD_CONTENT.replace("Batch Test", "Second"), encoding="utf-8")
    (d / "doc3.txt").write_text("# Plain Text\n\n## Section\n\nSome content here.\n", encoding="utf-8")
    return d


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "outputs"


def test_batch_xlsx_converts_all_files(input_dir, output_dir):
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--type", "xlsx",
    ])
    assert result.exit_code == 0, result.output
    xlsx_files = list(output_dir.glob("*.xlsx"))
    assert len(xlsx_files) == 3


def test_batch_creates_output_dir_if_absent(input_dir, tmp_path):
    out = tmp_path / "new" / "nested" / "dir"
    assert not out.exists()
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(input_dir),
        "--output-dir", str(out),
        "--type", "xlsx",
    ])
    assert result.exit_code == 0, result.output
    assert out.is_dir()


def test_batch_pattern_filters_files(input_dir, output_dir):
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--type", "xlsx",
        "--pattern", "*.md",
    ])
    assert result.exit_code == 0, result.output
    xlsx_files = list(output_dir.glob("*.xlsx"))
    assert len(xlsx_files) == 2


def test_batch_empty_dir_exits_zero(tmp_path, output_dir):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(empty),
        "--output-dir", str(output_dir),
        "--type", "xlsx",
    ])
    assert result.exit_code == 0
    assert "No supported files" in result.output


def test_batch_missing_input_dir_exits_nonzero(output_dir):
    result = runner.invoke(app, [
        "batch",
        "--input-dir", "/nonexistent/path",
        "--output-dir", str(output_dir),
        "--type", "xlsx",
    ])
    assert result.exit_code != 0


def test_batch_summary_reports_counts(input_dir, output_dir):
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--type", "xlsx",
    ])
    assert result.exit_code == 0, result.output
    assert "3/3 succeeded" in result.output


def test_batch_pptx_uses_bundled_template(input_dir, output_dir):
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--type", "pptx",
        "--no-validate",
    ])
    assert result.exit_code == 0, result.output
    pptx_files = list(output_dir.glob("*.pptx"))
    assert len(pptx_files) == 3
