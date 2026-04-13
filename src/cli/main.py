"""
Text2OfficeProcessor CLI — entry point for the text2officeprocessor command-line tool.

Usage:
    text2officeprocessor convert --input input.md --template template.pptx --output output.pptx --type pptx
    text2officeprocessor convert --input input.md --template template.docx --output output.docx --type docx
    text2officeprocessor convert --input input.md --output output.xlsx --type xlsx
    text2officeprocessor convert --slides-md slides.md --template template.pptx --output out.pptx --type pptx
    text2officeprocessor convert --slides-md slides.md --template template.pptx --output out.pptx --config my-rules.yaml
    text2officeprocessor analyze template.pptx
    text2officeprocessor batch --input-dir ./content/ --output-dir ./outputs/ --type pptx --template template.pptx
    text2officeprocessor batch --input-dir ./content/ --output-dir ./outputs/ --type xlsx
    text2officeprocessor drawio-export diagram.drawio --output diagram.png
    text2officeprocessor serve [--host 0.0.0.0] [--port 8000]
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
from src.core.exceptions import Text2OfficeProcessorError
from src.core.llm.runtime_config import resolve_provider_selection
from src.core.llm.providers import build_provider
from src.core.models import OutputFormat
from src.core.parser.preprocessor import InputPreprocessor
from src.core.planner.content_planner import ContentPlanner
from src.core.validation.validator import ProgrammaticValidator

app = typer.Typer(
    name="text2officeprocessor",
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
        None, "--llm", help="LLM provider: ollama | vllm | openai | claude | openrouter | groq | none."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Model name for the LLM provider."
    ),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation after rendering."),
    llm_validate: bool = typer.Option(
        False, "--llm-validate/--no-llm-validate",
        help="Run an LLM semantic coherence check after rendering (requires --llm).",
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to a custom rules YAML file (overrides config/default_rules.yaml).",
    ),
    log_level: str = typer.Option("info", "--log-level", help="Logging level: debug | info | warning."),
) -> None:
    """Convert an input document to PPTX, DOCX, or XLSX."""
    _setup_logging(log_level)
    logger = logging.getLogger("text2officeprocessor.cli")

    # -- Resolve LLM provider (local-first; configurable)
    provider = None
    resolved_llm_name, llm_config = resolve_provider_selection(llm_provider, llm_model)
    if resolved_llm_name:
        try:
            provider = build_provider(resolved_llm_name, llm_config)
            logger.info("Using LLM provider: %s", resolved_llm_name)
        except Exception as exc:
            logger.warning(
                "Could not initialize LLM provider '%s': %s — proceeding without LLM.",
                resolved_llm_name,
                exc,
            )

    resolved_template = _resolve_template(template, output_type)
    if resolved_template and resolved_template != template:
        typer.echo(f"  Using bundled template: {resolved_template.name}")

    llm_validator = None
    if llm_validate and provider:
        from src.core.validation.validator import LLMValidator
        llm_validator = LLMValidator(provider=provider)
    elif llm_validate and not provider:
        typer.echo("  [WARN] --llm-validate requires --llm to be set. Skipping LLM validation.")

    try:
        if output_type == OutputFormat.PPTX:
            _run_pptx(input_file, slides_md, resolved_template, output, provider, validate, config, logger, llm_validator)
        elif output_type == OutputFormat.DOCX:
            _run_docx(input_file, resolved_template, output, provider, validate, config, logger, llm_validator)
        elif output_type == OutputFormat.XLSX:
            _run_xlsx(input_file, output, provider, validate, logger, llm_validator)
    except Text2OfficeProcessorError as exc:
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
    llm_validator=None,
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

    if llm_validator:
        from src.core.validation.validator import LLMValidator
        llm_result = llm_validator.validate(result_path)
        typer.echo("  LLM semantic validation:")
        ProgrammaticValidator().print_report(llm_result)


def _run_docx(
    input_file: Optional[Path],
    template: Optional[Path],
    output: Path,
    provider,
    validate: bool,
    config: Optional[Path],
    logger: logging.Logger,
    llm_validator=None,
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

    if llm_validator:
        llm_result = llm_validator.validate(result_path)
        typer.echo("  LLM semantic validation:")
        ProgrammaticValidator().print_report(llm_result)


def _run_xlsx(
    input_file: Optional[Path],
    output: Path,
    provider,
    validate: bool,
    logger: logging.Logger,
    llm_validator=None,
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

    if llm_validator:
        llm_result = llm_validator.validate(result_path)
        typer.echo("  LLM semantic validation:")
        ProgrammaticValidator().print_report(llm_result)


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
        None, "--llm", help="LLM provider: ollama | vllm | openai | claude | openrouter | groq | none."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Model name for the LLM provider."
    ),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation after each render."),
    llm_validate: bool = typer.Option(
        False, "--llm-validate/--no-llm-validate",
        help="Run an LLM semantic coherence check after each render (requires --llm).",
    ),
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
    logger = logging.getLogger("text2officeprocessor.batch")

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

    # Resolve LLM provider once for the whole batch (local-first; configurable)
    provider = None
    resolved_llm_name, llm_config = resolve_provider_selection(llm_provider, llm_model)
    if resolved_llm_name:
        try:
            provider = build_provider(resolved_llm_name, llm_config)
            logger.info("Using LLM provider: %s", resolved_llm_name)
        except Exception as exc:
            logger.warning(
                "Could not initialize LLM provider '%s': %s — proceeding without LLM.",
                resolved_llm_name,
                exc,
            )

    resolved_template = _resolve_template(template, output_type)
    if resolved_template and resolved_template != template:
        typer.echo(f"  Using bundled template: {resolved_template.name}")

    llm_validator = None
    if llm_validate and provider:
        from src.core.validation.validator import LLMValidator
        llm_validator = LLMValidator(provider=provider)
    elif llm_validate and not provider:
        typer.echo("  [WARN] --llm-validate requires --llm to be set. Skipping LLM validation.")

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
                _run_pptx(input_file, None, resolved_template, output_file, provider, validate, config, logger, llm_validator)
            elif output_type == OutputFormat.DOCX:
                _run_docx(input_file, resolved_template, output_file, provider, validate, config, logger, llm_validator)
            elif output_type == OutputFormat.XLSX:
                _run_xlsx(input_file, output_file, provider, validate, logger, llm_validator)
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


@app.command("watch")
def watch(
    input_file: Path = typer.Option(
        ..., "--input", "-i", help="Input .md / .txt / .html file to watch."
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
    output_type: OutputFormat = typer.Option(
        OutputFormat.PPTX, "--type", help="Output format: pptx | docx | xlsx."
    ),
    template: Optional[Path] = typer.Option(
        None, "--template", "-t",
        help="Template .pptx or .docx file. Omit to use the bundled generic template.",
    ),
    slides_md: Optional[Path] = typer.Option(
        None, "--slides-md", "-s",
        help="Pre-authored slides markdown. Watched alongside --input when provided.",
    ),
    llm_provider: Optional[str] = typer.Option(
        None, "--llm", help="LLM provider for normalization."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Model name for the LLM provider."
    ),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation after each regeneration."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to a custom rules YAML file."
    ),
    debounce: float = typer.Option(
        1.0, "--debounce", help="Seconds to wait after a change before regenerating (default: 1.0)."
    ),
    log_level: str = typer.Option("info", "--log-level", help="Logging level: debug | info | warning."),
) -> None:
    """Watch an input file and auto-regenerate the output on every save."""
    _setup_logging(log_level)
    logger = logging.getLogger("text2officeprocessor.watch")

    if not input_file.exists():
        typer.echo(f"[ERROR] Input file not found: {input_file}", err=True)
        raise typer.Exit(code=1)

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        typer.echo("[ERROR] watchdog is not installed. Run: pip install watchdog", err=True)
        raise typer.Exit(code=1)

    provider = None
    resolved_llm_name, llm_cfg = resolve_provider_selection(llm_provider, llm_model)
    if resolved_llm_name:
        try:
            provider = build_provider(resolved_llm_name, llm_cfg)
            logger.info("Using LLM provider: %s", resolved_llm_name)
        except Exception as exc:
            logger.warning("Could not initialize LLM provider '%s': %s", resolved_llm_name, exc)

    resolved_template = _resolve_template(template, output_type)
    if resolved_template and resolved_template != template:
        typer.echo(f"  Using bundled template: {resolved_template.name}")

    # Files to monitor (deduped)
    watched_files = {input_file.resolve()}
    if slides_md:
        watched_files.add(slides_md.resolve())

    import threading
    import time

    _timer: list = [None]
    _lock = threading.Lock()

    def _regenerate() -> None:
        typer.echo(f"\n[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] Change detected — regenerating...")
        try:
            if output_type == OutputFormat.PPTX:
                _run_pptx(input_file, slides_md, resolved_template, output, provider, validate, config, logger)
            elif output_type == OutputFormat.DOCX:
                _run_docx(input_file, resolved_template, output, provider, validate, config, logger)
            elif output_type == OutputFormat.XLSX:
                _run_xlsx(input_file, output, provider, validate, logger)
            typer.echo("  Done.")
        except Exception as exc:
            typer.echo(f"  [ERROR] {exc}", err=True)

    def _schedule_regenerate() -> None:
        with _lock:
            if _timer[0] is not None:
                _timer[0].cancel()
            _timer[0] = threading.Timer(debounce, _regenerate)
            _timer[0].start()

    class _ChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if Path(event.src_path).resolve() in watched_files:
                _schedule_regenerate()

        def on_created(self, event):
            if Path(event.src_path).resolve() in watched_files:
                _schedule_regenerate()

    # Run once immediately on start
    _regenerate()

    watch_dirs = {p.parent for p in watched_files}
    observer = Observer()
    handler = _ChangeHandler()
    for d in watch_dirs:
        observer.schedule(handler, str(d), recursive=False)

    observer.start()
    file_list = ", ".join(p.name for p in watched_files)
    typer.echo(f"\nWatching: {file_list}  (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
        typer.echo("\nWatch mode stopped.")
    finally:
        observer.join()


@app.command("drawio-export")
def drawio_export(
    input_file: Path = typer.Argument(..., help="Source .drawio file to export."),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output PNG path. Defaults to <input>.png alongside the source file.",
    ),
    scale: str = typer.Option("2", "--scale", "-s", help="Export scale factor (default: 2 for 2x resolution)."),
    border: str = typer.Option("10", "--border", "-b", help="Border width in pixels around the diagram."),
    transparent: bool = typer.Option(False, "--transparent/--no-transparent", help="Transparent PNG background."),
    page: Optional[int] = typer.Option(None, "--page", "-p", help="1-based page index (default: first page)."),
    all_pages: bool = typer.Option(False, "--all-pages", help="Export every page as separate PNGs."),
    log_level: str = typer.Option("info", "--log-level", help="Logging level: debug | info | warning."),
) -> None:
    """Export a .drawio diagram to PNG using the drawio CLI."""
    _setup_logging(log_level)

    from src.core.drawio.converter import (
        DrawioExportError,
        export_all_pages,
        export_drawio_to_png,
    )

    if not input_file.exists():
        typer.echo(f"[ERROR] File not found: {input_file}", err=True)
        raise typer.Exit(code=1)

    try:
        if all_pages:
            out_dir = output if output and output.is_dir() else input_file.parent
            paths = export_all_pages(input_file, output_dir=out_dir, scale=scale, border=border)
            for p in paths:
                typer.echo(f"  Exported: {p}")
        else:
            path = export_drawio_to_png(
                input_file,
                output_path=output,
                page_index=page,
                scale=scale,
                border=border,
                transparent=transparent,
            )
            typer.echo(f"  Exported: {path}")
    except DrawioExportError as exc:
        typer.echo(f"\n[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"\n[ERROR] Unexpected error: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command("templates")
def list_templates() -> None:
    """List the bundled generic templates included with text2officeprocessor."""
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


@app.command("extract-styles")
def extract_styles_cmd(
    template: Path = typer.Argument(..., exists=True, readable=True, help="Path to .docx or .pptx template."),
    output: Path = typer.Option(..., "--output", "-o", help="Output JSON file path."),
) -> None:
    """Extract the complete visual identity from a template into a JSON style sheet."""
    from src.core.extraction.style_extractor import extract_styles
    try:
        stylesheet = extract_styles(template)
        stylesheet.save(output)
        style_count = len(stylesheet.styles) if stylesheet.styles else len(stylesheet.slide_layouts)
        typer.echo(f"  Extracted {style_count} styles/layouts → {output}")
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)


@app.command("extract")
def extract_cmd(
    source: Path = typer.Argument(..., exists=True, readable=True, help="Path to .docx, .pptx, or .xlsx file."),
    output_dir: Path = typer.Option(..., "--output", "-o", help="Output directory for extracted files."),
    no_styles: bool = typer.Option(False, "--no-styles", help="Skip style extraction."),
    no_media: bool = typer.Option(False, "--no-media", help="Skip media extraction."),
) -> None:
    """Extract content, styles, and media from an Office file into Markdown."""
    from src.core.extraction.content_extractor import extract_content
    try:
        content_path = extract_content(
            source, output_dir,
            extract_styles=not no_styles,
            extract_media=not no_media,
        )
        typer.echo(f"  Content → {content_path}")
        if not no_styles:
            suffix = source.suffix.lower()
            styles_name = "pptx_styles.json" if suffix == ".pptx" else "styles.json"
            sp = output_dir / styles_name
            if sp.exists():
                typer.echo(f"  Styles  → {sp}")
        media_dir = output_dir / "media"
        if media_dir.exists() and any(media_dir.iterdir()):
            count = sum(1 for _ in media_dir.iterdir())
            typer.echo(f"  Media   → {media_dir}/ ({count} files)")
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)


@app.command("diff-styles")
def diff_styles_cmd(
    before: Path = typer.Argument(..., exists=True, readable=True, help="First styles.json file."),
    after: Path = typer.Argument(..., exists=True, readable=True, help="Second styles.json file."),
) -> None:
    """Compare two extracted style sheets and show differences."""
    import json as _json
    try:
        a = _json.loads(before.read_text(encoding="utf-8"))
        b = _json.loads(after.read_text(encoding="utf-8"))

        a_styles = {s["style_id"]: s for s in a.get("styles", [])}
        b_styles = {s["style_id"]: s for s in b.get("styles", [])}

        added = set(b_styles) - set(a_styles)
        removed = set(a_styles) - set(b_styles)
        common = set(a_styles) & set(b_styles)

        changes_found = False
        for sid in sorted(added):
            typer.echo(f"ADDED    {sid} ({b_styles[sid].get('name', '')})")
            changes_found = True
        for sid in sorted(removed):
            typer.echo(f"REMOVED  {sid} ({a_styles[sid].get('name', '')})")
            changes_found = True
        for sid in sorted(common):
            if a_styles[sid] != b_styles[sid]:
                typer.echo(f"CHANGED  {sid}")
                _diff_dict(a_styles[sid], b_styles[sid], prefix="  ")
                changes_found = True

        if not changes_found:
            typer.echo("No style differences found.")
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)


def _diff_dict(a: dict, b: dict, prefix: str = "") -> None:
    """Print key-level differences between two dicts."""
    all_keys = sorted(set(list(a.keys()) + list(b.keys())))
    for key in all_keys:
        va, vb = a.get(key), b.get(key)
        if va != vb:
            typer.echo(f"{prefix}{key}: {va!r} → {vb!r}")


@app.command("analyze-template")
def analyze_template_cmd(
    template: Path = typer.Argument(..., exists=True, readable=True, help="Path to .docx or .pptx template."),
) -> None:
    """Print a summary of a template's styles, layouts, and fonts."""
    from src.core.extraction.style_extractor import extract_styles
    try:
        ss = extract_styles(template)
        typer.echo(f"\n  Template: {ss.source_file}")
        typer.echo(f"  Format:   {ss.format.upper()}")
        typer.echo(f"  Theme:    major={ss.theme.major_font or 'n/a'}  minor={ss.theme.minor_font or 'n/a'}")
        typer.echo(f"  Colors:   {len(ss.theme.colors)} theme colors")

        if ss.format == "docx":
            typer.echo(f"  Styles:   {len(ss.styles)}")
            typer.echo(f"  Numbering: {len(ss.numbering_defs)} definitions")
            if ss.section_properties:
                sp = ss.section_properties
                typer.echo(f"  Page:     {sp.page_width_pt:.0f}x{sp.page_height_pt:.0f}pt ({sp.orientation})")
                typer.echo(f"  Margins:  L={sp.margin_left_pt:.0f} R={sp.margin_right_pt:.0f} T={sp.margin_top_pt:.0f} B={sp.margin_bottom_pt:.0f}")
            # Show key paragraph styles
            para_styles = [s for s in ss.styles if s.style_type == "paragraph"]
            typer.echo(f"\n  Paragraph styles ({len(para_styles)}):")
            for s in para_styles[:20]:
                font_info = ""
                if s.font:
                    parts = []
                    if s.font.name:
                        parts.append(s.font.name)
                    if s.font.size_pt:
                        parts.append(f"{s.font.size_pt}pt")
                    if s.font.bold:
                        parts.append("bold")
                    if s.font.color:
                        parts.append(s.font.color)
                    font_info = " — " + ", ".join(parts) if parts else ""
                typer.echo(f"    {s.style_id}: {s.name}{font_info}")

        elif ss.format == "pptx":
            typer.echo(f"  Slides:   {len(ss.slide_layouts)}")
            w_in = ss.slide_width_emu / 914400
            h_in = ss.slide_height_emu / 914400
            typer.echo(f"  Size:     {w_in:.1f}\" x {h_in:.1f}\"")
            typer.echo(f"\n  Slide layouts:")
            for layout in ss.slide_layouts:
                typer.echo(f"    [{layout.index}] {layout.name} — {len(layout.placeholders)} shapes")
                for ph in layout.placeholders[:5]:
                    typer.echo(f"        {ph.name}: {ph.type} ({ph.width_pt:.0f}x{ph.height_pt:.0f}pt)")

        typer.echo("")
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (default: 127.0.0.1)."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port (default: 8000)."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development only)."),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level."),
) -> None:
    """Start the Text2OfficeProcessor web UI server."""
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "[ERROR] Web UI requires extra dependencies. Install with:\n"
            "  pip install text2officeprocessor[web]\n"
            "or: pip install fastapi 'uvicorn[standard]' python-multipart",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"\nText2OfficeProcessor Web UI — http://{host}:{port}\nPress Ctrl+C to stop.\n")
    uvicorn.run(
        "src.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
