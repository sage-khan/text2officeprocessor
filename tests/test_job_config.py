"""
Tests for the unified job configuration (src/core/job_config.py) and its
wiring into the CLI's --config flag.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typer.testing import CliRunner

from src.cli.main import app
from src.core.job_config import JobConfig, load_job_config, pick

runner = CliRunner()


# ---------------------------------------------------------------------------
# load_job_config
# ---------------------------------------------------------------------------

def test_load_job_config_none_path_returns_empty():
    cfg = load_job_config(None)
    assert cfg == JobConfig()


def test_load_job_config_reads_job_section(tmp_path):
    yaml_file = tmp_path / "job.yaml"
    yaml_file.write_text(
        "job:\n"
        "  input: content.md\n"
        "  template: template.pptx\n"
        "  output: out.pptx\n"
        "  type: pptx\n"
        "  validate: false\n"
        "  llm_validate: true\n"
        "  overflow_strategy: shrink\n"
        "  log_level: debug\n",
        encoding="utf-8",
    )
    cfg = load_job_config(yaml_file)
    assert cfg.input == Path("content.md")
    assert cfg.template == Path("template.pptx")
    assert cfg.output == Path("out.pptx")
    assert cfg.output_type == "pptx"
    assert cfg.validate is False
    assert cfg.llm_validate is True
    assert cfg.overflow_strategy == "shrink"
    assert cfg.log_level == "debug"


def test_load_job_config_reads_batch_fields(tmp_path):
    yaml_file = tmp_path / "job.yaml"
    yaml_file.write_text(
        "job:\n"
        "  input_dir: ./content\n"
        "  output_dir: ./outputs\n"
        "  pattern: '*.md'\n"
        "  fail_fast: true\n",
        encoding="utf-8",
    )
    cfg = load_job_config(yaml_file)
    assert cfg.input_dir == Path("./content")
    assert cfg.output_dir == Path("./outputs")
    assert cfg.pattern == "*.md"
    assert cfg.fail_fast is True


def test_load_job_config_reads_llm_section(tmp_path):
    yaml_file = tmp_path / "job.yaml"
    yaml_file.write_text(
        "llm:\n"
        "  default_provider: claude\n"
        "  providers:\n"
        "    claude:\n"
        "      model: claude-3-5-sonnet-20241022\n"
        "      api_key: sk-ant-inline\n",
        encoding="utf-8",
    )
    cfg = load_job_config(yaml_file)
    assert cfg.llm_provider == "claude"
    assert cfg.llm_settings["providers"]["claude"]["api_key"] == "sk-ant-inline"


def test_load_job_config_explicit_llm_provider_wins_over_default_provider(tmp_path):
    yaml_file = tmp_path / "job.yaml"
    yaml_file.write_text(
        "job:\n"
        "  llm_provider: openai\n"
        "llm:\n"
        "  default_provider: claude\n",
        encoding="utf-8",
    )
    cfg = load_job_config(yaml_file)
    assert cfg.llm_provider == "openai"


def test_load_job_config_missing_sections_returns_defaults(tmp_path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("validation:\n  strict: true\n", encoding="utf-8")
    cfg = load_job_config(yaml_file)
    assert cfg.input is None
    assert cfg.llm_settings == {}


# ---------------------------------------------------------------------------
# pick — CLI overrides config
# ---------------------------------------------------------------------------

def test_pick_prefers_cli_value_when_given():
    assert pick("cli", "config") == "cli"


def test_pick_falls_back_to_config_value():
    assert pick(None, "config") == "config"


def test_pick_returns_none_when_both_unset():
    assert pick(None, None) is None


def test_pick_cli_false_wins_over_config_true():
    # Explicit CLI False must not be treated as "unset" — only None means unset.
    assert pick(False, True) is False


# ---------------------------------------------------------------------------
# End-to-end: `convert --config job.yaml` with no other flags
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# Report

## Section One

| Metric | Value |
|--------|-------|
| Revenue | 100 |
"""


def test_convert_from_config_only(tmp_path):
    input_md = tmp_path / "content.md"
    input_md.write_text(SAMPLE_MD, encoding="utf-8")
    output_xlsx = tmp_path / "out.xlsx"

    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        f"job:\n"
        f"  input: {input_md}\n"
        f"  output: {output_xlsx}\n"
        f"  type: xlsx\n"
        f"llm:\n"
        f"  default_provider: none\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["convert", "--config", str(job_yaml)])
    assert result.exit_code == 0, result.output
    assert output_xlsx.exists()


def test_convert_cli_output_overrides_config_output(tmp_path):
    input_md = tmp_path / "content.md"
    input_md.write_text(SAMPLE_MD, encoding="utf-8")
    config_output = tmp_path / "config-out.xlsx"
    cli_output = tmp_path / "cli-out.xlsx"

    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        f"job:\n"
        f"  input: {input_md}\n"
        f"  output: {config_output}\n"
        f"  type: xlsx\n"
        f"llm:\n"
        f"  default_provider: none\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["convert", "--config", str(job_yaml), "--output", str(cli_output)]
    )
    assert result.exit_code == 0, result.output
    assert cli_output.exists()
    assert not config_output.exists()


def test_convert_missing_output_and_config_output_errors():
    result = runner.invoke(app, ["convert", "--slides-md", "nonexistent.md"])
    assert result.exit_code == 1
    assert "--output is required" in result.output
