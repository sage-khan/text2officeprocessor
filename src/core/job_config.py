"""
src/core/job_config.py

Unified job configuration for the CLI.

A single YAML file passed via `--config` can supply everything the
`convert` / `batch` / `watch` commands would otherwise need as separate
flags — input/template/output paths, output type, LLM provider selection
(including inline API keys or a local endpoint's base_url), and the
validate/overflow-strategy switches — under a `job:` and `llm:` section:

    job:
      input: content.md
      template: templates/my-template.pptx
      output: outputs/deck.pptx
      type: pptx
      validate: true
      overflow_strategy: auto

    llm:
      default_provider: claude
      providers:
        claude:
          model: claude-3-5-sonnet-20241022
          api_key: sk-ant-...          # optional; falls back to ANTHROPIC_API_KEY
        ollama:
          base_url: http://localhost:11434
          model: llama3.2:1b

The same file may still carry the pre-existing rules sections
(`validation`, `sanitization`, `placeholder_map`, `llm_validation`, ...)
consumed elsewhere via `config_loader.load_config()` — the whole file is
also passed straight through to `ContentPlanner`/`ProgrammaticValidator`
as `config_path`, so one file covers both concerns.

Explicit CLI flags always win over values from this file — see `pick()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.core.config_loader import load_config


@dataclass
class JobConfig:
    input: Optional[Path] = None
    slides_md: Optional[Path] = None
    template: Optional[Path] = None
    output: Optional[Path] = None
    output_type: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    validate: Optional[bool] = None
    llm_validate: Optional[bool] = None
    overflow_strategy: Optional[str] = None
    log_level: Optional[str] = None

    # batch-only
    input_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    pattern: Optional[str] = None
    fail_fast: Optional[bool] = None

    # watch-only
    debounce: Optional[float] = None

    # raw `llm:` section — {default_provider, providers: {...}} — passed straight
    # through to resolve_provider_selection() as an override for llm_config.yaml.
    llm_settings: dict[str, Any] = field(default_factory=dict)


def load_job_config(config_path: Optional[Path]) -> JobConfig:
    """Load the `job:` and `llm:` sections of a --config YAML file, if present."""
    if config_path is None:
        return JobConfig()

    raw = load_config(config_path)
    job = raw.get("job")
    job = job if isinstance(job, dict) else {}
    llm_settings = raw.get("llm")
    llm_settings = llm_settings if isinstance(llm_settings, dict) else {}

    def _path(key: str) -> Optional[Path]:
        value = job.get(key)
        return Path(value) if value is not None else None

    return JobConfig(
        input=_path("input"),
        slides_md=_path("slides_md"),
        template=_path("template"),
        output=_path("output"),
        output_type=job.get("type"),
        llm_provider=job.get("llm_provider") or llm_settings.get("default_provider"),
        llm_model=job.get("llm_model"),
        validate=job.get("validate"),
        llm_validate=job.get("llm_validate"),
        overflow_strategy=job.get("overflow_strategy"),
        log_level=job.get("log_level"),
        input_dir=_path("input_dir"),
        output_dir=_path("output_dir"),
        pattern=job.get("pattern"),
        fail_fast=job.get("fail_fast"),
        debounce=job.get("debounce"),
        llm_settings=llm_settings,
    )


def pick(cli_value: Any, job_value: Any) -> Any:
    """An explicit CLI flag always wins; otherwise fall back to the job config value."""
    return cli_value if cli_value is not None else job_value
