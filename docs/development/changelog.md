# Changelog

All changes are recorded here with timestamps. Append-only.

---

## [0.1.0] — 2026-04-07

### Initial Release

**Architecture established:**
- Full pipeline: `.md` / `.txt` / `.html` → `.pptx` / `.docx` / `.xlsx`
- `InputPreprocessor` — encoding-safe parser for markdown, plain text, HTML
- `LLMNormalizer` — semantic tagging with rule-based fallback; supports Ollama, OpenAI, Claude, OpenRouter, Groq
- `ContentPlanner` — maps normalized sections to `SlideDefinition` objects; also parses canonical `## SLIDE N` format directly
- `PPTXEngine` — SlidePart cloning method; three-layer text replacement; background preservation verified
- `DOCXEngine` — template body injection; image/logo preservation; in-order body iteration
- `XLSXEngine` — openpyxl structured mapping; auto column widths; header freeze
- `ProgrammaticValidator` — artifact checks, placeholder checks, file size heuristics
- `CLI` (Typer) — `md2office convert` and `md2office analyze` commands

**Test results (2026-04-07):**
- 38/38 unit and integration tests pass
- End-to-end PPTX test: 22 slides, 2.08 MB, all backgrounds preserved, validation passed
- All slide types verified visually: Section Header, Video Title, Multi-Point, Key Highlights 4-col, Excellence Grid, Stats, Single Point, Callout, Next Video

**Test data:**
- Generic `sample-slides.md` and `sample-sections.pptx` used as primary e2e fixtures (bundled under `tests/`)

---

## [0.1.1] — 2026-04-07

### Added

**Text overflow auto-shrink (`fit_text_to_shape`):**
- Post-injection step on every slide in `PPTXEngine._render_slide()`
- Estimates overflow via bounding box geometry (character count vs. shape width × height)
- Reduces run font sizes in 2pt steps until content fits or `min_font_size_pt` (default 8pt) is reached
- Skips shapes with `MSO_AUTO_SIZE` already set by the template
- Recurses into group shapes
- Config knobs exposed in `config/default_rules.yaml` under `text_overflow:`
- Fix: `PP_AUTO_SIZE` → `MSO_AUTO_SIZE` (enum renamed in python-pptx 1.x)

**Docker support:**
- `Dockerfile` — multi-stage build (builder + slim runtime); non-root `appuser`; `/data` volume mount point
- `docker-compose.yml` — `md2office` service + optional `ollama` sidecar (behind `llm` profile)
- `.dockerignore` — excludes venv, tests, outputs, secrets, IDE files
- Image builds successfully: `docker build -t md2office .`

**CLI invokable from anywhere:**
- `pip install -e .` registers `md2office` binary in the venv
- Shell wrapper script `md2office` at project root for PATH-based invocation
- Fixed `pyproject.toml` build backend from `setuptools.backends.legacy:build` → `setuptools.build_meta` for compatibility with older setuptools

**Documentation:**
- `docs/guide.md` fully rewritten as a coherent narrative document (removed raw chat transcript)
- Sections added: Invoking the Tool, Text Overflow Handling, Running with Docker

**Git / release:**
- Repository: `git@github.com:sage-khan/text2officeprocessor.git`
- `main` branch set as default; holds the last stable release
- `dev` branch is the active development branch; all work goes here first
- Tagged `v0.1.0` on `main`

---

## [0.2.0] — 2026-04-07

### Added

**PyPI-ready packaging:**
- `pyproject.toml` URLs corrected to `sage-khan/text2officeprocessor`
- `src/data/` package created to hold bundled templates and config inside the Python package tree
- `[tool.setuptools.package-data]` wired to include `*.pptx`, `*.docx`, `*.yaml` from `src.data`
- `MANIFEST.in` added for sdist completeness
- Wheel verified: `src/data/templates/` and `src/data/config/` present in `md2office-0.2.0-py3-none-any.whl`

**Bundled generic templates (`templates/` + `src/data/templates/`):**
- `generic-slides.pptx` — 13-slide template bank matching all `DEFAULT_TEMPLATE_MAP` intents; placeholder strings align exactly with `config/default_rules.yaml`
- `generic-document.docx` — branded DOCX template with Heading 1/2/3 and List Bullet styles
- Generated deterministically via `scripts/create_bundled_templates.py` (committed, reproducible)

**CLI improvements:**
- `md2office templates` subcommand — lists all bundled templates with slide counts and paths
- `--template` is now optional for PPTX and DOCX; falls back to bundled template automatically
- `_resolve_template()` uses `importlib.resources` for PyPI installs; falls back to file path for editable installs
- Bundled template auto-selection printed to stdout: `Using bundled template: generic-slides.pptx`

---

## [0.2.1] — 2026-04-07

### Improved

**Full DOM-aware HTML parser (`src/core/parser/preprocessor.py`):**
- Replaced the basic tag-stripping HTMLParser with a proper `lxml`-based DOM parser
- `<h1>`–`<h6>` headings now create `DocumentSection` boundaries with correct level
- `<ul>` / `<ol>` → `ContentType.LIST` with per-`<li>` items
- `<table>` with `<thead>`/`<tbody>` → `ContentType.TABLE` with `headers` + `rows`
- `<img src>` → `ContentType.IMAGE` with `path` and `alt` keys
- `<p>`, `<blockquote>`, `<pre>` → `ContentType.PARAGRAPH` with inline tags (`<strong>`, `<em>`, `<a>`) collapsed to plain text
- `<script>` and `<style>` blocks removed from DOM before any processing (XSS-safe)
- Container tags (`<div>`, `<section>`, `<article>`, `<main>`) are recursed into transparently
- `_parse_html_fallback()` retained as last-resort for lxml parse failures
- `<html><title>` used as document title if no `<h1>` is present

**Tests:**
- 6 new HTML-specific tests added: headings, lists, tables, inline formatting, images, script/style exclusion
- Total test count: **44 passed**

**Known limitations (Phase 2 scope):**
- Draw.io flowchart → PNG → slide insertion not yet implemented
- LLM validation pass (semantic coherence check) not yet wired
- Batch processing CLI not yet implemented
- No web UI
