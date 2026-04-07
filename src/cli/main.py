"""
MD2Office CLI — entry point for the md2office command-line tool.

Usage:
    md2office convert --input input.md --template template.pptx --output output.pptx --type pptx
    md2office convert --input input.md --template template.docx --output output.docx --type docx
    md2office convert --input input.md --output output.xlsx --type xlsx
    md2office convert --slides-md slides.md --template template.pptx --output out.pptx --type pptx
    md2office convert --slides-md slides.md --template template.pptx --output out.pptx --config my-rules.yaml
    md2office analyze template.pptx
    md2office batch --input-dir ./content/ --output-dir ./outputs/ --type pptx --template template.pptx
    md2office batch --input-dir ./content/ --output-dir ./outputs/ --type xlsx
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from src.core.engines.docx.engine import DOCXEngine
from src.core.engines.pptx.engine import PPTXEngine
from src.core.engines.xlsx.engine import XLSXEngine
from src.core.exceptions import MD2OfficeError
from src.core.llm.providers import build_provider
from src.core.models import OutputFormat
from src.core.parser.preprocessor import InputPreprocessor
from src.core.planner.content_planner import ContentPlanner
from src.core.validation.validator import ProgrammaticValidator

app = typer.Typer(
    name="md2office",
    help="Convert markdown / text / HTML to PPTX, DOCX, or XLSX using template-driven rendering.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Bundled template resolution
# Supports both editable installs (src/data/templates/) and installed packages
# (via importlib.resources).
# ---------------------------------------------------------------------------

def _bundled_templates_dir() -> Path:
    """Return the directory containing bundled templates, regardless of install method."""
    try:
        from importlib.resources import files
        return Path(str(files("src.data").joinpath("templates")))
    except Exception:
        return Path(__file__).parent.parent / "data" / "templates"


def _resolve_template(template: Optional[Path], output_type: "OutputFormat") -> Optional[Path]:
    """Return the template path, falling back to the bundled generic template."""
    if template:
        return template
    tdir = _bundled_templates_dir()
    pptx = tdir / "generic-slides.pptx"
    docx = tdir / "generic-document.docx"
    if output_type.value == "pptx" and pptx.exists():
        return pptx
    if output_type.value == "docx" and docx.exists():
        return docx
    return None

LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        level=LOG_LEVELS.get(level.lower(), logging.INFO),
    )


@app.command("convert")
def convert(
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i", help="Input .md / .txt / .html file."
    ),
    slides_md: Optional[Path] = typer.Option(
        None, "--slides-md", "-s",
        help="Pre-authored slides markdown file (## SLIDE N format). Bypasses LLM normalization.",
    ),
    template: Optional[Path] = typer.Option(
        None, "--template", "-t",
        help="Template .pptx or .docx file. Omit to use the bundled generic template.",
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
    output_type: OutputFormat = typer.Option(
        OutputFormat.PPTX, "--type", help="Output format: pptx | docx | xlsx."
    ),
    llm_provider: Optional[str] = typer.Option(
        None, "--llm", help="LLM provider: ollama | openai | claude | openrouter | groq."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Model name for the LLM provider."
    ),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation after rendering."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to a custom rules YAML file (overrides config/default_rules.yaml).",
    ),
    log_level: str = typer.Option("info", "--log-level", help="Logging level: debug | info | warning."),
) -> None:
    """Convert an input document to PPTX, DOCX, or XLSX."""
    _setup_logging(log_level)
    logger = logging.getLogger("md2office.cli")

    # -- Resolve LLM provider (optional)
    provider = None
    if llm_provider:
        try:
            llm_config = {}
            if llm_model:
                llm_config["model"] = llm_model
            provider = build_provider(llm_provider, llm_config)
            logger.info("Using LLM provider: %s", llm_provider)
        except Exception as exc:
            logger.warning("Could not initialize LLM provider '%s': %s — proceeding without LLM.", llm_provider, exc)

    resolved_template = _resolve_template(template, output_type)
    if resolved_template and resolved_template != template:
        typer.echo(f"  Using bundled template: {resolved_template.name}")

    try:
        if output_type == OutputFormat.PPTX:
            _run_pptx(input_file, slides_md, resolved_template, output, provider, validate, config, logger)
        elif output_type == OutputFormat.DOCX:
            _run_docx(input_file, resolved_template, output, provider, validate, config, logger)
        elif output_type == OutputFormat.XLSX:
            _run_xlsx(input_file, output, provider, validate, logger)
    except MD2OfficeError as exc:
        typer.echo(f"\n[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        logger.exception("Unexpected error during conversion")
        typer.echo(f"\n[ERROR] Unexpected error: {exc}", err=True)
        raise typer.Exit(code=1)


def _run_pptx(
    input_file: Optional[Path],
    slides_md: Optional[Path],
    template: Optional[Path],
    output: Path,
    provider,
    validate: bool,
    config: Optional[Path],
    logger: logging.Logger,
) -> None:
    from src.core.llm.normalizer import LLMNormalizer

    if not template:
        typer.echo("[ERROR] --template is required for PPTX output.", err=True)
        raise typer.Exit(code=1)

    if slides_md:
        # Direct mode: parse pre-authored slides markdown
        logger.info("Using pre-authored slides markdown: %s", slides_md)
        plan = ContentPlanner.parse_slides_markdown(slides_md)
    elif input_file:
        # Full pipeline mode
        logger.info("Running full pipeline on: %s", input_file)
        preprocessor = InputPreprocessor()
        parsed = preprocessor.parse(input_file)

        normalizer = LLMNormalizer(provider=provider)
        normalized = normalizer.normalize(parsed)

        planner = ContentPlanner(config_path=config)
        plan = planner.plan_slides(parsed, normalized)
    else:
        typer.echo("[ERROR] Either --input or --slides-md is required.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"  Slides to render: {len(plan.slides)}")
    engine = PPTXEngine()
    result_path = engine.render(plan, template, output)
    typer.echo(f"  Output written: {result_path}")

    if validate:
        validator = ProgrammaticValidator()
        validation = validator.validate_pptx(result_path)
        validator.print_report(validation)


def _run_docx(
    input_file: Optional[Path],
    template: Optional[Path],
    output: Path,
    provider,
    validate: bool,
    config: Optional[Path],
    logger: logging.Logger,
) -> None:
    if not input_file:
        typer.echo("[ERROR] --input is required for DOCX output.", err=True)
        raise typer.Exit(code=1)
    if not template:
        typer.echo("[ERROR] --template is required for DOCX output.", err=True)
        raise typer.Exit(code=1)

    preprocessor = InputPreprocessor()
    parsed = preprocessor.parse(input_file)
    plan = ContentPlanner.plan_document(parsed)

    typer.echo(f"  Sections to render: {len(plan.sections)}")
    engine = DOCXEngine()
    result_path = engine.render(plan, template, output)
    typer.echo(f"  Output written: {result_path}")

    if validate:
        validator = ProgrammaticValidator()
        validation = validator.validate_docx(result_path)
        validator.print_report(validation)


def _run_xlsx(
    input_file: Optional[Path],
    output: Path,
    provider,
    validate: bool,
    logger: logging.Logger,
) -> None:
    if not input_file:
        typer.echo("[ERROR] --input is required for XLSX output.", err=True)
        raise typer.Exit(code=1)

    preprocessor = InputPreprocessor()
    parsed = preprocessor.parse(input_file)
    plan = ContentPlanner.plan_spreadsheet(parsed)

    typer.echo(f"  Sheets to render: {len(plan.sheets)}")
    engine = XLSXEngine()
    result_path = engine.render(plan, output)
    typer.echo(f"  Output written: {result_path}")

    if validate:
        validator = ProgrammaticValidator()
        validation = validator.validate_xlsx(result_path)
        validator.print_report(validation)


@app.command("analyze")
def analyze(
    template: Path = typer.Argument(..., help="Template .pptx file to analyze."),
    log_level: str = typer.Option("info", "--log-level", help="Logging level."),
) -> None:
    """Analyze a PPTX template: list all slides, shapes, and text runs."""
    _setup_logging(log_level)

    if not template.exists():
        typer.echo(f"[ERROR] Template not found: {template}", err=True)
        raise typer.Exit(code=1)

    try:
        from pptx import Presentation
    except ImportError:
        typer.echo("[ERROR] python-pptx is not installed.", err=True)
        raise typer.Exit(code=1)

    prs = Presentation(str(template))
    typer.echo(f"\nTemplate: {template.name}")
    typer.echo(f"Total slides: {len(prs.slides)}\n")

    for i, slide in enumerate(prs.slides):
        typer.echo(f"=== SLIDE {i} (layout: {slide.slide_layout.name}) ===")
        for j, shape in enumerate(slide.shapes):
            if shape.has_text_frame:
                for k, para in enumerate(shape.text_frame.paragraphs):
                    for r, run in enumerate(para.runs):
                        if run.text.strip():
                            typer.echo(
                                f'  Shape {j} "{shape.name}" para[{k}] run[{r}]: {repr(run.text)}'
                            )
        typer.echo("")


@app.command("batch")
def batch(
    input_dir: Path = typer.Option(
        ..., "--input-dir", "-i",
        help="Directory containing input files (.md / .txt / .html).",
    ),
    output_dir: Path = typer.Option(
        ..., "--output-dir", "-o",
        help="Directory where output files will be written (created if absent).",
    ),
    output_type: OutputFormat = typer.Option(
        OutputFormat.PPTX, "--type", help="Output format: pptx | docx | xlsx."
    ),
    template: Optional[Path] = typer.Option(
        None, "--template", "-t",
        help="Template .pptx or .docx file. Omit to use the bundled generic template.",
    ),
    glob_pattern: str = typer.Option(
        "*", "--pattern", "-p",
        help="Glob pattern to filter input files, e.g. '*.md' or 'section-*.html'.",
    ),
    llm_provider: Optional[str] = typer.Option(
        None, "--llm", help="LLM provider: ollama | openai | claude | openrouter | groq."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Model name for the LLM provider."
    ),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation after each render."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to a custom rules YAML file.",
    ),
    fail_fast: bool = typer.Option(
        False, "--fail-fast/--no-fail-fast",
        help="Stop immediately on first error instead of continuing with remaining files.",
    ),
    log_level: str = typer.Option("info", "--log-level", help="Logging level: debug | info | warning."),
) -> None:
    """Convert every input file in a directory to the chosen output format."""
    _setup_logging(log_level)
    logger = logging.getLogger("md2office.batch")

    if not input_dir.is_dir():
        typer.echo(f"[ERROR] Input directory not found: {input_dir}", err=True)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect candidate files matching the pattern and supported formats
    supported_suffixes = {".md", ".txt", ".html", ".htm"}
    candidates = sorted(
        f for f in input_dir.glob(glob_pattern)
        if f.is_file() and f.suffix.lower() in supported_suffixes
    )

    if not candidates:
        typer.echo(
            f"[WARN] No supported files found in '{input_dir}' matching '{glob_pattern}'. "
            "Supported extensions: .md .txt .html .htm"
        )
        raise typer.Exit(code=0)

    # Resolve LLM provider once for the whole batch
    provider = None
    if llm_provider:
        try:
            llm_config = {}
            if llm_model:
                llm_config["model"] = llm_model
            provider = build_provider(llm_provider, llm_config)
            logger.info("Using LLM provider: %s", llm_provider)
        except Exception as exc:
            logger.warning(
                "Could not initialize LLM provider '%s': %s — proceeding without LLM.",
                llm_provider, exc,
            )

    resolved_template = _resolve_template(template, output_type)
    if resolved_template and resolved_template != template:
        typer.echo(f"  Using bundled template: {resolved_template.name}")

    ext_map = {OutputFormat.PPTX: ".pptx", OutputFormat.DOCX: ".docx", OutputFormat.XLSX: ".xlsx"}
    out_ext = ext_map[output_type]

    total = len(candidates)
    succeeded: list[Path] = []
    failed: list[tuple[Path, str]] = []

    typer.echo(f"\nBatch: {total} file(s) → {output_type.value.upper()} in '{output_dir}'\n")

    for idx, input_file in enumerate(candidates, start=1):
        output_file = output_dir / (input_file.stem + out_ext)
        typer.echo(f"  [{idx}/{total}] {input_file.name} → {output_file.name}")
        try:
            if output_type == OutputFormat.PPTX:
                _run_pptx(input_file, None, resolved_template, output_file, provider, validate, config, logger)
            elif output_type == OutputFormat.DOCX:
                _run_docx(input_file, resolved_template, output_file, provider, validate, config, logger)
            elif output_type == OutputFormat.XLSX:
                _run_xlsx(input_file, output_file, provider, validate, logger)
            succeeded.append(output_file)
        except Exception as exc:
            msg = str(exc)
            failed.append((input_file, msg))
            typer.echo(f"    [FAILED] {msg}", err=True)
            if fail_fast:
                typer.echo("\n[ABORTED] --fail-fast is set. Stopping batch.", err=True)
                raise typer.Exit(code=1)

    # Summary
    typer.echo(f"\n{'='*50}")
    typer.echo(f"Batch complete: {len(succeeded)}/{total} succeeded, {len(failed)} failed.")
    if failed:
        typer.echo("\nFailed files:")
        for path, reason in failed:
            typer.echo(f"  {path.name}: {reason}")
        raise typer.Exit(code=1)


@app.command("templates")
def list_templates() -> None:
    """List the bundled generic templates included with md2office."""
    typer.echo("\nBundled templates (use with --template or omit for auto-selection):\n")

    found_any = False
    for path in sorted(_bundled_templates_dir().glob("*")):
        if path.suffix not in (".pptx", ".docx"):
            continue
        found_any = True
        size_kb = path.stat().st_size // 1024
        if path.suffix == ".pptx":
            try:
                from pptx import Presentation
                prs = Presentation(str(path))
                detail = f"{len(prs.slides)} slides"
            except Exception:
                detail = "PPTX"
        else:
            detail = "DOCX"
        typer.echo(f"  {path.name:<35} {detail:<15} {size_kb} KB")
        typer.echo(f"  Path: {path}\n")

    if not found_any:
        typer.echo("  No bundled templates found. Run: python scripts/create_bundled_templates.py")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
