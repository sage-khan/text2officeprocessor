# Changelog

All changes are recorded here with timestamps. Append-only.

---

## [0.5.0] — 2026-07-19

### Added — `set_big_statement()` for Single-Bullet "Pull-Quote" Slides

A one-bullet placeholder (`SlideDefinition.template_index == 2`-style Single Point
pattern) is small, left-aligned, and top-anchored by default — dropping one long sentence
into it verbatim leaves most of the slide empty and reads as an afterthought rather than a
deliberate choice (real feedback from a course-deck review, 2026-07-19: several slides
built this way looked broken/unfinished).

`set_big_statement(slide, text)` (`src/core/engines/pptx/engine.py`) fills that same
placeholder as a large (22-30pt, tiered by text length), bold, centred, bullet-free
statement instead — a deliberate, scoped exception to "never move shapes," used only for
this one pattern: the body shape is resized/recentred to a generous content area and the
placeholder's inherited bullet-glyph definition (`buChar`/`buAutoNum`) is stripped and
replaced with `buNone`, the same phantom-glyph cleanup `set_bullets()` already does for
unused paragraph slots.

Wired into the render pipeline via a new `SlideDefinition.big_statement: str` field
(`src/core/models.py`) — when set, the engine calls `set_big_statement()` automatically,
the same way `bullets` triggers `set_bullets()`. New regression test:
`test_set_big_statement_centers_text_and_removes_bullet_glyph`.

### Documentation — Diagram Legibility, Structural Auditing, and Label-Overlap Guidance

`md2office-rules.md` §§1.10.10-1.10.14 (and its `.cursor/rules/` mirror) now cover lessons
from a real full-course diagram/slide review pass (2026-07-19):

- Audit slide plans by inspecting the actual resolved `SlideDefinition` objects
  (`template_index`, `len(bullets)`, `diagram_path`, `big_statement`), never by grepping
  human-readable labels in markdown source — inconsistent labelling across authoring
  passes silently defeats a label-text audit.
- `definition`-style one-liner slides are for genuine `term: definition` pairs, not prose —
  an average line length above ~70 characters is the signal to double-check by hand.
- Diagram/injected-image text must be legible **after** the scale-down a wide source
  canvas undergoes to fit the slide's content area, not just legible in isolation at native
  resolution — verify on the full-resolution rendered slide image, never a thumbnail
  montage alone.
- Two concrete label-overlap fixes for after a legibility edit: widen the gap between
  connected shapes (or move a label off a connector into a free-standing text element) when
  an auto-generated connector label fully covers a short line; add an explicit offset (or
  wrap instead of widen) when enlarging text causes adjacent parallel labels to collide.
- All of the above are now listed as mandatory steps of the final PPTX-deliverable review,
  not optional follow-up.

---

## [0.4.2] — 2026-07-19

### Fixed — `duplicate_slide()` Silently Dropping Cloned Images (Wrong-Relationship-ID Bug)

**The most significant fix in this release.** `duplicate_slide()` copied a source
slide's relationships onto the new slide part using `new_part.rels.get_or_add(rel.reltype,
rel._target)`. `get_or_add()` mints a **fresh** rId for each relationship rather than
preserving the original one. The deep-copied slide XML, however, still contains its
original hardcoded references (e.g. `<a:blip r:embed="rId2">` inside a picture
placeholder) — if the new part's relationships get renumbered relative to the original
(which happens whenever a slide has 2+ relationships, e.g. an image rel plus the
slideLayout rel, and is a near-coin-flip depending on the two relationships' order in the
source file), that `r:embed` reference now resolves to the WRONG relationship — often the
slideLayout instead of the image. The picture then fails to load and the shape silently
falls back to its own solid-fill placeholder colour, rendering as a plain grey/blank panel
where a real image should be, with no error or warning anywhere in the pipeline.

This was found by direct visual inspection (not caught by any prior automated check) on a
real EC-Council course template's "Excellence Grid" bank slide, whose picture placeholder
has exactly this two-relationship shape. Confirmed non-deterministic: the same bug,
present in the library the whole time, rendered correctly on one sibling course's
already-built deck (lucky relationship ordering in that particular source file) and
visibly broken on another's — so a deck "looking fine" in one visual spot-check is not
proof this bug didn't affect a different slide, or a different template file, elsewhere.

**Fix**: relationships are now copied by directly inserting a `_Relationship` object into
`new_part.rels._rels` keyed by the **original** rId, preserving the exact
rId → (reltype, target) mapping the cloned XML expects. Regression test:
`test_duplicate_slide_preserves_relationship_ids` (constructs the same shape as the real
bug — clones a bank slide with 2+ relationships and asserts every rId/reltype/target
survives the clone unchanged).

**If you have existing decks built with this library before 2026-07-19**, any deck that
used a cloned slide with more than one relationship (most commonly: any slide type with a
picture placeholder, since those always have an image rel *and* a layout rel) may have a
blank/grey panel where an image should be. This is not something re-running validation
catches — it requires an actual visual (LibreOffice → PDF → PNG, or open in PowerPoint)
re-check of any deck built before this fix.

### Fixed — Phantom Bullet Markers and Uncapped Overflow Shrink

**`set_bullets()` no longer leaves phantom bullet markers (`src/core/engines/pptx/engine.py`):**
- Real, reported defect: when a caller supplies fewer bullets than a template's
  multi-paragraph bullet box has paragraph slots (the common "12 paragraphs,
  fill the first N" Multi Point pattern), the unused paragraphs previously had
  only their run text blanked, not the paragraph itself removed. An empty
  `<a:p>` can still carry an explicit `<a:buChar>`/`<a:buAutoNum>` bullet-glyph
  definition in its `<a:pPr>`, inherited from the template's list style — some
  renderers draw that glyph even with no text next to it, producing bullet
  markers with nothing in them. Fixed by removing the unused paragraph (or, for
  the sibling-shape-per-bullet pattern, the unused shape) from the XML entirely
  once bullets are assigned, rather than leaving an empty-but-still-bulleted
  slot behind. Regression test: `test_set_bullets_removes_unused_paragraphs`.

**Overflow auto-shrink now respects a per-run cap relative to the template's own size (`fit_text_to_shape_single`):**
- Previously, `fit_text_to_shape_single` shrank overflowing text down to a
  single absolute floor (`MIN_FONT_SIZE_PT = 8`) regardless of the template's
  original size for that run — a 28pt heading could end up shrunk all the way
  to 8pt to force an over-long paragraph to fit, which reads as "a different,
  smaller typeface was used here" rather than "the same slide, slightly
  denser." Added `MAX_SHRINK_FROM_ORIGINAL_PT = 6`: each run now has its own
  floor of `max(MIN_FONT_SIZE_PT, its_own_original_size - 6)`, captured before
  any shrinking begins. Past that point the loop stops and logs a warning
  recommending the content be shortened instead of shrunk further. Regression
  test: `test_fit_text_to_shape_never_shrinks_more_than_cap_below_original`.

### Documentation
- Added slide-authoring guidance to `docs/development/template-layout-analysis.md`
  (or successor rule docs) on: never repeating the same `template_index` more
  than twice consecutively across a deck (engagement/variety), preferring
  transparent-background diagram exports (`drawio --export --transparent`)
  with a bordered fallback when transparency isn't achievable, a "definition
  slide" pattern (one-liner text with no bullet glyph, diagram placed below),
  and a mandatory per-slide pre-planning pass (pick `template_index`, draft
  the exact text, decide whether an image/diagram is needed, decide whether
  content is tabular) before any slide is actually built.

---

## [0.4.1] — 2026-06-08

### Added — PPTX Overflow Handling + LLM Spreadsheet Reorganizer

**PPTX Content Fitting (NEW):**
- Four overflow handling strategies: `summarize` (LLM condense), `split` (multi-slide), `shrink` (font reduce), `auto` (LLM selects)
- Configurable via `pptx.overflow_strategy` in `default_rules.yaml`
- Per-strategy thresholds: `max_body_chars`, `max_bullet_chars`, `max_slide_total_chars`
- High-capacity layout selection for dense content
- New CLI flag: `--overflow-strategy {summarize,split,shrink,auto}`

**`PPTXContentFitter` class (`src/core/engines/pptx/content_fitter.py`):**
- `fit_content()` — analyzes content density and applies selected strategy
- `fit_slide_plan()` — processes entire SlidePlan, may increase slide count for split strategy
- LLM-powered summarization with metric preservation rules
- Rule-based splitting with intelligent chunking

**LLM-Powered Spreadsheet Reorganizer (NEW):**
- `SpreadsheetReorganizer` class (`src/core/planner/spreadsheet_reorganizer.py`)
- Consolidates fragmented section-per-sheet mapping into logical business tables
- Creates "Dashboard" sheet with KPIs when quantitative data detected
- Table fingerprinting to group similar tables (e.g., Regional + Product breakdowns)
- LLM prompt template for intelligent data organization
- Rule-based fallback when LLM unavailable (KPI extraction, table consolidation)

**Configuration additions (`default_rules.yaml`):**
- `spreadsheet_reorganizer.enabled` — enable/disable LLM reorganization
- `spreadsheet_reorganizer.max_sheets` — limit fragmentation
- `spreadsheet_reorganizer.table_types` — dashboard, breakdown, timeline, comparison, matrix, raw
- `pptx_summarizer.enabled` + thresholds for LLM condensing
- Full prompt templates for both reorganizer and summarizer

**CLI updates:**
- `--overflow-strategy` flag for PPTX conversion
- `_run_pptx()` now passes `overflow_strategy` and `llm_provider` to `PPTXEngine`
- `_run_xlsx()` now passes `llm_provider` to `ContentPlanner.plan_spreadsheet()`

**`ContentPlanner.plan_spreadsheet()` signature change:**
- Now accepts `llm_provider: Any | None = None` parameter
- Uses LLM reorganizer when provider available, falls back to rule-based consolidation
- Still supports original section-per-sheet mapping as final fallback

---

## [0.4.0] — 2026-04-13

### Added — Extraction Pipeline & Pandoc Integration

Inspired by **edgemint** (Mansuy, Apache 2.0) style extraction architecture and
**opendataloader-pdf** hybrid processing model. See `docs/development/implementation-v2.md`.

**Style Extraction (`src/core/extraction/style_extractor.py`)**
- DOCX → `ExtractedStyleSheet`: parses styles.xml (fonts, sizes, colors, bold/italic,
  alignment, spacing, indentation), numbering.xml, theme1.xml, section properties
- PPTX → `ExtractedStyleSheet`: extracts all slide layouts with placeholder geometry
  (position, size, type, font), slide dimensions, and theme colors/fonts
- Shared theme parser for both formats (major/minor fonts, 12+ color slots)
- JSON serialization with None-stripping for clean output

**Content Extraction (`src/core/extraction/content_extractor.py`)**
- DOCX → Markdown: Pandoc preferred (fenced divs, bracketed spans), python-docx fallback
- PPTX → canonical `## SLIDE N — template_index: N` format (round-trip ready)
- XLSX → Markdown tables (one section per sheet)
- Embedded media extraction (images from DOCX/PPTX ZIP archives)
- Styles + content + media extracted in one call

**Data Models (`src/core/extraction/models.py`)**
- `ExtractedStyleSheet` root container with JSON serialization
- `DocxStyle`, `FontProperties`, `ParagraphFormat`, `SectionProperties`
- `PptxSlideLayout`, `PlaceholderInfo` with EMU → pt conversion
- `NumberingDef`, `NumberingLevel`, `ThemeInfo`

**DOCX Engine Pandoc Integration (`src/core/engines/docx/engine.py`)**
- Dual rendering: Pandoc `--reference-doc` (preferred) + python-docx (fallback)
- `DOCXEngine(use_pandoc=True|False|None)` constructor for explicit control
- `_plan_to_markdown()` converts DocPlan to clean Markdown for Pandoc
- Auto-detect Pandoc availability, graceful fallback on failure

**New CLI Commands (`src/cli/main.py`)**
- `extract-styles <template> -o styles.json` — full visual identity extraction
- `extract <file> -o dir/` — content + styles + media extraction
- `analyze-template <template>` — template summary (styles, layouts, fonts, page size)
- `diff-styles before.json after.json` — style version comparison

**Tests (35 new, 164 total)**
- `test_style_extractor.py`: DOCX/PPTX extraction, JSON serialization, model units
- `test_content_extractor.py`: round-trip extraction for all 3 formats, CLI smoke tests
- Fixed flaky `test_cli_llm_validate_without_llm_warns` assertion

---

## [0.3.0] — 2026-04-07

### Added / Changed

**Launch readiness hardening (backend + web UI):**
- Fixed web drag/drop upload path to attach dropped file to the real form input (not label-only UI state).
- Added `output_name` support in `POST /convert`, with safe filename sanitization.
- Added UI output filename field and explicit browser-download/save behavior messaging.
- Added explicit startup dependency guard for `python-multipart`.

**LLM runtime architecture update (local-first):**
- Added `VLLMProvider` in `src/core/llm/providers.py`.
- Added `.env` loading for provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `VLLM_API_KEY`) without overwriting existing env vars.
- Added `src/core/llm/runtime_config.py` to resolve provider/model via `config/llm_config.yaml` (default provider + per-provider model/base_url).
- CLI and web runtime now use config-driven local-first provider resolution; `none` explicitly disables LLM.

**Config and local deployment workflow:**
- Updated both runtime and bundled `llm_config.yaml` to include vLLM provider block.
- Default local model updated to `llama3.1:8b` for Ollama.
- Added `.env.example` and tracked it via `.gitignore` allowlist.
- Added backend switch/run scripts:
  - `scripts/switch-llm-backend.sh` (one-command backend switch, optional service start)
  - `scripts/run-vllm-external.sh` (run vLLM with external cache path)
- Added vLLM Docker Compose profile in `docker-compose.yml`.

**Backend robustness:**
- XLSX engine now sanitizes invalid worksheet title characters and guarantees unique sheet names.

**Tests:**
- Added `tests/test_llm_runtime_config.py` (provider resolution + vLLM factory support).
- Added web test for custom output filename.
- Added XLSX test for sheet name sanitization and uniqueness.

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
- `CLI` (Typer) — `text2officeprocessor convert` and `text2officeprocessor analyze` commands

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
- `docker-compose.yml` — `text2officeprocessor` service + optional `ollama` sidecar (behind `llm` profile)
- `.dockerignore` — excludes venv, tests, outputs, secrets, IDE files
- Image builds successfully: `docker build -t text2officeprocessor .`

**CLI invokable from anywhere:**
- `pip install -e .` registers `text2officeprocessor` binary in the venv
- Shell wrapper script `text2officeprocessor` at project root for PATH-based invocation
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
- Wheel verified: `src/data/templates/` and `src/data/config/` present in `text2officeprocessor-0.2.0-py3-none-any.whl`

**Bundled generic templates (`templates/` + `src/data/templates/`):**
- `generic-slides.pptx` — 13-slide template bank matching all `DEFAULT_TEMPLATE_MAP` intents; placeholder strings align exactly with `config/default_rules.yaml`
- `generic-document.docx` — branded DOCX template with Heading 1/2/3 and List Bullet styles
- Generated deterministically via `scripts/create_bundled_templates.py` (committed, reproducible)

**CLI improvements:**
- `text2officeprocessor templates` subcommand — lists all bundled templates with slide counts and paths
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

---

## [0.2.2] — 2026-04-07

### Added

**`text2officeprocessor batch` command (`src/cli/main.py`):**
- Converts every supported file (`.md`, `.txt`, `.html`, `.htm`) in a directory to the chosen output format
- `--input-dir` / `--output-dir` — source and destination; output dir created automatically
- `--type pptx | docx | xlsx` — output format (default: pptx)
- `--template` — optional; falls back to bundled template for PPTX/DOCX
- `--pattern` — glob filter e.g. `*.md` or `section-*.html` (default: `*`)
- `--llm` / `--llm-model` — optional LLM normalisation applied to every file
- `--config` — custom rules YAML applied to every file
- `--fail-fast` — abort on first error (default: continue and report all failures at end)
- `--validate/--no-validate` — run `ProgrammaticValidator` after each render
- Final summary line: `Batch complete: N/M succeeded, K failed.`
- Non-zero exit code if any file fails; zero if all succeed or directory is empty

**Tests:**
- 7 new batch tests: full conversion, output-dir auto-creation, glob filtering, empty dir, missing dir, summary count, bundled template fallback
- Total test count: **51 passed**

---

## [0.2.3] — 2026-04-07

### Added

**Draw.io → PPTX diagram embedding (`src/core/drawio/converter.py`):**
- `export_drawio_to_png()` — calls `drawio --export --format png`; wraps with `xvfb-run` on headless Linux automatically
- `export_all_pages()` — exports every page of a multi-page diagram as separate PNGs
- `_detect_page_count()` — counts `<diagram>` elements in XML to determine page count
- `DrawioExportError` — raised for missing CLI, non-zero exit, or empty output
- Falls back to cwd-relative path resolution for `diagram_path` in slides markdown

**Slides markdown `- diagram:` key:**
- Any slide definition can include `- diagram: "path/to/file.drawio"` (or `.png`/`.jpg`)
- `ContentPlanner.parse_slides_markdown` parses this into `SlideDefinition.diagram_path`
- `SlideIntent` set to `DIAGRAM` automatically when `diagram_path` is present

**PPTX engine embedding (`PPTXEngine._embed_diagram`, `_insert_image_centred`):**
- `.drawio` files are exported to a temporary PNG via `export_drawio_to_png`, then embedded
- `.png`/`.jpg`/`.jpeg`/`.gif`/`.bmp` files are embedded directly
- Image is centred on the slide with a 0.5" margin, preserving aspect ratio
- Missing file or export failure → warning log only (slide still rendered without image)

**`text2officeprocessor drawio-export` CLI command:**
- Exports a `.drawio` file to PNG directly from the command line
- `--scale`, `--border`, `--transparent`, `--page`, `--all-pages` options
- Usable independently of the PPTX pipeline

**Tests:**
- 9 new draw.io tests: missing file, CLI unavailable, non-zero exit, success mock, page count, planner parsing, engine embedding
- Total test count: **60 passed**

---

## [0.2.4] — 2026-04-07

### Added

**LLM semantic validation pass (`src/core/validation/validator.py`):**
- `LLMValidator` class — optional post-render semantic coherence check via any configured LLM provider
- Extracts full text from `.pptx` (slide-by-slide), `.docx` (paragraphs), `.xlsx` (cells) and sends to LLM
- Prompt instructs the model to return a JSON array of issues with `severity`, `location`, `issue_type`, `message` fields
- Five issue types: `TRUNCATED`, `GARBLED`, `PLACEHOLDER_LEAK`, `MISMATCH`, `EMPTY_SECTION`
- `_parse_llm_response()` — tolerates markdown fences, trailing prose, embedded arrays, malformed JSON (never raises)
- Content truncated to 8 000 chars before sending to avoid context window overflow
- All failures (LLM unavailable, malformed response, extraction error) return an empty `ValidationResult` — never blocks the pipeline

**CLI `--llm-validate` flag:**
- Available on both `convert` and `batch` commands
- Requires `--llm` to be set; prints a `[WARN]` and skips silently if no provider is configured
- LLM validation report printed alongside the programmatic validation report

**Tests:**
- 11 new LLM validator tests: JSON parsing (clean, fenced, embedded, malformed), provider mocked validate (no issues, with issues, LLM failure, unsupported format, missing file), CLI warn-on-no-provider
- Total test count: **71 passed**

---

## [0.2.5] — 2026-04-07

### Added

**`text2officeprocessor watch` command (`src/cli/main.py`):**
- Watches an input file (`.md`, `.txt`, `.html`) and auto-regenerates the output on every save
- `--input` / `--output` / `--type` — same semantics as `convert`
- `--slides-md` — if provided, also watched; any save triggers a rebuild
- `--template` — optional; falls back to bundled template for PPTX/DOCX
- `--debounce N` — wait N seconds after the last change before regenerating (default: 1.0 s); debounce collapses rapid saves into one regeneration
- `--validate/--no-validate` — programmatic validation after each rebuild
- `--llm` / `--llm-model` — LLM normalization applied to each rebuild
- Runs one immediate conversion on startup before entering the watch loop
- Graceful `Ctrl+C` handling (prints "Watch mode stopped.")
- Uses `watchdog` for efficient inotify-based file monitoring; directory polled at the parent-dir level
- `watchdog` added to core dependencies (`requirements.txt`, `pyproject.toml v0.2.4`)

**Tests:**
- 5 new watch tests: missing input exits non-zero, output created on startup, "Watching" message, PPTX bundled template, debounce collapses rapid events
- Total test count: **76 passed**

---

## [0.2.6] — 2026-04-07

### Added

**Web UI (`src/web/app.py`, `text2officeprocessor serve`):**
- Browser interface at `GET /` — drag-and-drop or click-to-browse, output format selector, LLM provider/model fields, download link
- `GET /health` — JSON health check
- `POST /convert` — multipart upload, returns the converted file as an attachment
- Bundled templates auto-selected for PPTX/DOCX; temporary files cleaned up via BackgroundTask
- Input/output validation: unsupported types return HTTP 422
- FastAPI optional extra: `pip install text2officeprocessor[web]`

**`text2officeprocessor serve` CLI command:**
- `--host`, `--port`, `--reload`, `--log-level` options
- Prints `Text2OfficeProcessor Web UI — http://host:port` on startup
- Clean ImportError message if `fastapi`/`uvicorn` not installed

**Dependencies:**
- `web` optional extra: `fastapi>=0.110.0`, `uvicorn[standard]>=0.29.0`, `python-multipart>=0.0.9`
- `httpx>=0.27.0` added to `dev` extras (required by FastAPI TestClient)

**Tests:**
- 10 new web tests: health, HTML UI, md/txt/html to xlsx, md to pptx/docx bundled, unsupported input/output (422), filename stem preserved
- Total test count: **86 passed**

---

## [0.2.7] — 2026-04-07

### Added

**Centralised config loader (`src/core/config_loader.py`):**
- `load_config(path?)` — resolves config in order: explicit path → `config/default_rules.yaml` → bundled `src/data/config/default_rules.yaml`
- `get(cfg, *keys, default=None)` — safe nested dict accessor with fallback
- Results cached with `lru_cache` to avoid repeated disk reads
- Graceful error handling: missing or malformed YAML returns `{}` with a warning log

**Config-driven validation (`config/default_rules.yaml`, `src/data/config/default_rules.yaml`):**
- New `validation.markdown_artifacts` list — replaces hardcoded `MARKDOWN_ARTIFACTS`
- New `validation.known_placeholders` list — replaces hardcoded `KNOWN_TEMPLATE_PLACEHOLDERS`
- New `validation.pptx_min_size_bytes` key — replaces hardcoded `PPTX_MIN_SIZE_BYTES`
- New `validation.check_artifacts`, `check_placeholders`, `check_file_size` flags
- New `llm_validation.max_content_chars` key — replaces hardcoded `_MAX_CONTENT_CHARS = 8000`
- New `llm_validation.prompt` key — full prompt template in config, overridable per project
- `ProgrammaticValidator(config_path=None)` — reads all check settings from config; built-in lists remain as fallback defaults
- `LLMValidator(provider, config_path=None)` — reads prompt template and char limit from config

**`requirements.txt` overhaul:**
- Fully annotated with section comments
- Added: `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx` (previously missing)
- All optional sections labelled clearly (web, LLM providers, dev)

**`Dockerfile` fixes:**
- Version label bumped to `0.2.6`
- Builder stage installs web extras (`fastapi`, `uvicorn`, `python-multipart`, `httpx`) before `requirements.txt`
- `EXPOSE 8000` added for web UI
- `HEALTHCHECK` added: polls `GET /health` every 30s

**Tests — 37 new across two new test files:**
- `tests/test_config_loader.py` (17 tests): load default/explicit/missing/empty/malformed config; `get` helper; validator reads custom artifacts, placeholders, flags, min-size; LLMValidator reads custom max-chars, prompt, falls back to defaults
- `tests/test_robustness.py` (20 tests): CLI edge cases (missing input, xlsx no template, pptx bundled template, custom config, html input, analyze non-existent); validator xlsx/docx/missing-file smoke; web health JSON, empty file, large file, unknown output 422, no-file 422, form fields; batch output-dir creation, fail-fast; LLMValidator truncation from config
- Total test count: **123 passed**
