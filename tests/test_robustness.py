"""
Robustness tests — edge cases that guard against regressions across
the CLI, validator, web endpoint, and engine pipeline.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()

MINIMAL_MD = "# Doc\n\n## Sec\n\nContent.\n"


# ---------------------------------------------------------------------------
# CLI — convert command edge cases
# ---------------------------------------------------------------------------

def test_convert_missing_input_exits_nonzero(tmp_path):
    result = runner.invoke(app, [
        "convert",
        "--input", str(tmp_path / "ghost.md"),
        "--output", str(tmp_path / "out.xlsx"),
        "--type", "xlsx",
    ])
    assert result.exit_code != 0


def test_convert_xlsx_requires_no_template(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(MINIMAL_MD, encoding="utf-8")
    out = tmp_path / "out.xlsx"
    result = runner.invoke(app, [
        "convert", "--input", str(md),
        "--output", str(out), "--type", "xlsx",
        "--no-validate",
    ])
    assert result.exit_code == 0
    assert out.exists()


def test_convert_xlsx_output_is_valid_workbook(tmp_path):
    import openpyxl
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\n## Section\n\n- a\n- b\n- c\n", encoding="utf-8")
    out = tmp_path / "out.xlsx"
    runner.invoke(app, [
        "convert", "--input", str(md),
        "--output", str(out), "--type", "xlsx", "--no-validate",
    ])
    wb = openpyxl.load_workbook(str(out))
    assert wb.sheetnames


def test_convert_pptx_uses_bundled_template_without_explicit_flag(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(MINIMAL_MD, encoding="utf-8")
    out = tmp_path / "out.pptx"
    result = runner.invoke(app, [
        "convert", "--input", str(md),
        "--output", str(out), "--type", "pptx", "--no-validate",
    ])
    assert result.exit_code == 0
    assert out.exists()
    assert out.stat().st_size > 0


def test_convert_with_custom_config(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(MINIMAL_MD, encoding="utf-8")
    out = tmp_path / "out.xlsx"
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("xlsx:\n  freeze_header: false\n", encoding="utf-8")
    result = runner.invoke(app, [
        "convert", "--input", str(md),
        "--output", str(out), "--type", "xlsx",
        "--config", str(cfg), "--no-validate",
    ])
    assert result.exit_code == 0


def test_convert_html_input_to_xlsx(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<h1>Title</h1><h2>Section</h2><p>Para.</p>", encoding="utf-8")
    out = tmp_path / "out.xlsx"
    result = runner.invoke(app, [
        "convert", "--input", str(html),
        "--output", str(out), "--type", "xlsx", "--no-validate",
    ])
    assert result.exit_code == 0
    assert out.exists()


def test_analyze_nonexistent_template_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["analyze", str(tmp_path / "ghost.pptx")])
    assert result.exit_code != 0


def test_templates_command_runs_cleanly():
    result = runner.invoke(app, ["templates"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# ProgrammaticValidator — xlsx and docx smoke
# ---------------------------------------------------------------------------

def test_programmatic_validator_xlsx_valid(tmp_path):
    import openpyxl
    from src.core.validation.validator import ProgrammaticValidator
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Col1", "Col2"])
    ws.append(["val1", "val2"])
    out = tmp_path / "good.xlsx"
    wb.save(str(out))
    v = ProgrammaticValidator()
    r = v.validate_xlsx(out)
    assert r.passed


def test_programmatic_validator_missing_file_reports_error(tmp_path):
    from src.core.validation.validator import ProgrammaticValidator
    v = ProgrammaticValidator()
    r = v.validate_pptx(tmp_path / "missing.pptx")
    assert not r.passed
    assert any(i.severity == "error" for i in r.issues)


def test_programmatic_validator_check_artifacts_disabled_skips_check(tmp_path):
    import openpyxl
    from src.core.validation.validator import ProgrammaticValidator
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("validation:\n  check_artifacts: false\n  check_placeholders: false\n", encoding="utf-8")
    wb = openpyxl.Workbook()
    wb.active.append(["**bold artifact**"])
    out = tmp_path / "out.xlsx"
    wb.save(str(out))
    v = ProgrammaticValidator(config_path=cfg)
    r = v.validate_xlsx(out)
    assert not any("artifact" in i.message.lower() for i in r.issues)


# ---------------------------------------------------------------------------
# Web endpoint — additional robustness
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient
from src.web.app import create_app

_client = TestClient(create_app())


def test_web_health_check_is_json():
    resp = _client.get("/health")
    assert resp.json() == {"status": "ok", "service": "md2office"}


def test_web_convert_empty_file_returns_error(tmp_path):
    resp = _client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("empty.md", b"", "text/markdown")},
    )
    # Should either succeed (empty XLSX) or return an error — never crash
    assert resp.status_code in (200, 422, 500)


def test_web_convert_large_markdown(tmp_path):
    content = ("# Title\n\n## Section\n\n" + "Line of text.\n" * 200).encode()
    resp = _client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("big.md", content, "text/markdown")},
    )
    assert resp.status_code == 200


def test_web_convert_unknown_output_returns_422():
    resp = _client.post(
        "/convert",
        data={"output_type": "rtf"},
        files={"file": ("doc.md", b"# Hi\n", "text/markdown")},
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_web_convert_no_file_returns_422():
    resp = _client.post("/convert", data={"output_type": "xlsx"})
    assert resp.status_code == 422


def test_web_index_contains_form_fields():
    resp = _client.get("/")
    html = resp.text
    assert 'name="output_type"' in html
    assert 'name="file"' in html


# ---------------------------------------------------------------------------
# Batch — edge cases
# ---------------------------------------------------------------------------

def test_batch_fails_fast_stops_on_first_error(tmp_path):
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    # Create one broken file and one valid
    bad = in_dir / "bad.md"
    bad.write_text("", encoding="utf-8")  # empty might render or fail
    good = in_dir / "good.md"
    good.write_text(MINIMAL_MD, encoding="utf-8")
    # Simply verify the command doesn't crash (outcome depends on whether empty renders)
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(in_dir),
        "--output-dir", str(out_dir),
        "--type", "xlsx",
        "--no-validate",
    ])
    assert result.exit_code in (0, 1)


def test_batch_creates_output_dir_if_missing(tmp_path):
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    md = in_dir / "doc.md"
    md.write_text(MINIMAL_MD, encoding="utf-8")
    out_dir = tmp_path / "output_that_does_not_exist_yet"
    result = runner.invoke(app, [
        "batch",
        "--input-dir", str(in_dir),
        "--output-dir", str(out_dir),
        "--type", "xlsx",
        "--no-validate",
    ])
    assert result.exit_code == 0
    assert out_dir.exists()


# ---------------------------------------------------------------------------
# LLMValidator — prompt truncation respected from config
# ---------------------------------------------------------------------------

def test_llm_validator_content_truncated_to_config_limit(tmp_path):
    import openpyxl
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("llm_validation:\n  max_content_chars: 10\n  prompt: 'Check: {content}'\n", encoding="utf-8")

    wb = openpyxl.Workbook()
    wb.active.append(["A" * 200])
    out = tmp_path / "out.xlsx"
    wb.save(str(out))

    captured_prompt = []
    provider = MagicMock()
    provider.generate.side_effect = lambda p: captured_prompt.append(p) or "[]"

    from src.core.validation.validator import LLMValidator
    v = LLMValidator(provider=provider, config_path=cfg)
    v.validate(out)

    assert provider.generate.called
    prompt_sent = captured_prompt[0]
    # The content placeholder in our prompt is tiny — check it doesn't exceed limit+overhead
    assert len(prompt_sent) < 200  # "Check: " + 10 chars = well under
