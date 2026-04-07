# MD2Office — Intelligent Document Converter

> Convert **Markdown / Text / HTML** to **PPTX, DOCX, and XLSX** using template-driven deterministic rendering with optional LLM normalization.

[![PyPI](https://img.shields.io/pypi/v/md2office.svg)](https://pypi.org/project/md2office/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

MD2Office takes your content in plain text formats and converts it into professionally formatted office documents using **your own templates**. The tool preserves all template branding, backgrounds, images, and layouts exactly — it only injects your content at the run level.

| Input | Output |
|-------|--------|
| `.md` | `.pptx` — Template-driven slide decks |
| `.txt` | `.docx` — Branded word documents |
| `.html` | `.xlsx` — Structured spreadsheets |

### Core Design Principles

- **Deterministic rendering** — no LLM hallucination in the final output. All document construction is 100% programmatic.
- **Template preservation** — backgrounds, images, fonts, and layouts are never modified.
- **LLM as assistant, not author** — LLM can normalize and tag content, never write documents.
- **Zero magic** — every replacement is traceable; every slide is auditable.

---

## Quick Start

### Install

```bash
pip install md2office
```

The `md2office` command is immediately available. Bundled generic templates are included — no template file needed to get started.

**From source** (for development or contribution):

```bash
git clone https://github.com/sage-khan/text2officeprocessor
cd text2officeprocessor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

### Zero-config — try it immediately

No template file needed. The bundled generic template is used automatically:

```bash
md2office convert --slides-md slides.md --output outputs/presentation.pptx
```

See what templates are bundled:

```bash
md2office templates
```

### Generate a PPTX with your own template

```bash
md2office convert \
  --slides-md slides.md \
  --template  template.pptx \
  --output    outputs/presentation.pptx \
  --type pptx
```

### Generate from raw markdown (full pipeline)

```bash
md2office convert \
  --input content.md \
  --template template.pptx \
  --output output.pptx \
  --type pptx
```

### Generate DOCX

```bash
md2office convert \
  --input content.md \
  --template template.docx \
  --output output.docx \
  --type docx
```

### Generate XLSX

```bash
md2office convert \
  --input report.md \
  --output report.xlsx \
  --type xlsx
```

### Use a custom rules config

```bash
md2office convert \
  --slides-md slides.md \
  --template template.pptx \
  --output output.pptx \
  --config my-rules.yaml
```

### Batch convert an entire directory

```bash
md2office batch \
  --input-dir ./content/ \
  --output-dir ./outputs/ \
  --type xlsx
```

Convert only `.md` files to PPTX using your own template:

```bash
md2office batch \
  --input-dir ./slides/ \
  --output-dir ./outputs/ \
  --type pptx \
  --template template.pptx \
  --pattern "*.md"
```

### Embed a draw.io diagram into a slide

In your `slides.md`:

```markdown
## SLIDE 3 — template_index: 2 (Single Point)
- placeholder: "SINGLE POINT SLIDE" → "System Architecture"
- diagram: "diagrams/architecture.drawio"
```

Or export a diagram directly:

```bash
md2office drawio-export diagrams/architecture.drawio --output outputs/architecture.png
md2office drawio-export diagrams/multi-page.drawio --all-pages
```

### Watch mode — auto-regenerate on save

```bash
md2office watch \
  --input notes.md \
  --output presentation.pptx \
  --type pptx
```

Every time you save `notes.md`, the output is regenerated automatically. A 1-second debounce prevents multiple rapid saves from triggering redundant builds. Press `Ctrl+C` to stop.

```bash
md2office watch \
  --input slides.md \
  --output presentation.xlsx \
  --type xlsx \
  --debounce 0.5 \
  --no-validate
```

### LLM semantic validation

After rendering, ask an LLM to check the output for truncated text, unreplaced placeholders, content mismatches, and empty sections:

```bash
md2office convert \
  --slides-md slides.md \
  --output output.pptx \
  --llm ollama --llm-model mistral \
  --llm-validate
```

The check is non-blocking — if the LLM is unavailable the document is still saved.

### Web UI

Install the web extras and launch the browser interface:

```bash
pip install md2office[web]
md2office serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) — drag-and-drop a `.md`, `.txt`, or `.html` file, choose an output format, and download the result.

```bash
md2office serve --host 0.0.0.0 --port 8080
```

### Analyze a template before authoring

```bash
md2office analyze path/to/template.pptx
```

---

## Slides Markdown Format

The primary PPTX workflow uses a structured markdown format:

```markdown
## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Getting Started"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Key Points"
- bullets:
  - "First key point goes here"
  - "Second key point goes here"
  - "Third key point goes here"

---

## SLIDE 3 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "What You Will Learn"
- card_1_title: "Topic One"
- card_1_body: "Short description of topic one"
- card_2_title: "Topic Two"
- card_2_body: "Short description of topic two"
```

See [docs/guide.md](docs/guide.md) for the full format specification.

---

## Architecture

```
Input (.md / .txt / .html)
    │
    ▼
InputPreprocessor → ParsedDocument
    │
    ▼
LLMNormalizer (optional, fallback: rules) → [(SlideIntent, SlideContent)]
    │
    ▼
ContentPlanner → SlidePlan / DocPlan / SpreadsheetPlan
    │
    ├── PPTXEngine (SlidePart clone + inject)
    ├── DOCXEngine (template body injection)
    └── XLSXEngine (openpyxl structured mapping)
         │
         ▼
    ProgrammaticValidator
         │
         ▼
    Output (.pptx / .docx / .xlsx)
```

Full architecture diagram: [docs/architecture.drawio](docs/architecture.drawio)

---

## LLM Providers

LLM is entirely optional — the tool works fully offline with rule-based normalization.

| Provider | Flag | Required Env Var |
|----------|------|-----------------|
| Ollama (local) | `--llm ollama` | None |
| OpenAI | `--llm openai` | `OPENAI_API_KEY` |
| Claude | `--llm claude` | `ANTHROPIC_API_KEY` |
| OpenRouter | `--llm openrouter` | `OPENROUTER_API_KEY` |
| Groq | `--llm groq` | `GROQ_API_KEY` |

```bash
md2office convert --input content.md --template t.pptx \
  --output out.pptx --type pptx --llm ollama --llm-model mistral
```

---

## Tutorial: Converting Your First File

This section walks through the complete workflow for each output format — from zero to a finished document.

### Step 1 — Analyse your template

Before writing any content, run `analyze` on your template to discover the exact placeholder text strings in every shape. These are the strings you will reference in your slides markdown:

```bash
md2office analyze my-template.pptx
```

Sample output:

```
Template: my-template.pptx
Total slides: 13

=== SLIDE 0 (layout: Section Header) ===
  Shape 1 "Title" para[0] run[0]: 'Section Name Here'
  Shape 2 "Subtitle" para[0] run[0]: 'SECTION Number'

=== SLIDE 3 (layout: Multi Point) ===
  Shape 1 "Title" para[0] run[0]: 'Multi Point Slide'
```

The string in quotes (`'Section Name Here'`, `'Multi Point Slide'`, etc.) is what you put as the `"old"` value in a `placeholder:` line.

---

### Step 2 — Create your slides markdown

Create a file called `slides.md`. Each slide block starts with a header that names the template slide to clone and what content to inject:

```markdown
## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Project Overview"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Goals for This Quarter"
- bullets:
  - "Reduce onboarding time by 30%"
  - "Launch the self-service portal"
  - "Complete security audit"

---

## SLIDE 3 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "Four Pillars"
- placeholder: "Enter your subhead line here" → "Our strategic focus areas"
- card_1_title: "Speed"
- card_1_body: "Faster delivery cycles"
- card_2_title: "Quality"
- card_2_body: "Zero-defect release policy"
- card_3_title: "Scale"
- card_3_body: "Infrastructure for 10x growth"
- card_4_title: "People"
- card_4_body: "Invest in the team first"

---

## SLIDE 4 — template_index: 11 (Excellence Grid)
- placeholder: "EXCELLENCE IN THE" → "Why We Win"
- item_01_title: "Customer Focus"
- item_01_body: "Every decision starts with the customer."
- item_02_title: "Execution"
- item_02_body: "We ship and iterate fast."
- item_03_title: "Ownership"
- item_03_body: "Everyone is accountable."
```

**Key rules:**
- `template_index` is the zero-based slide number in your template (from `analyze` output)
- `placeholder: "old" → "new"` replaces exact text; `old` must match the template character for character
- Separate slides with `---`
- See [docs/guide.md](docs/guide.md) for all supported slide types and item keys

---

### Step 3 — Generate the PPTX

```bash
md2office convert \
  --slides-md slides.md \
  --template  my-template.pptx \
  --output    outputs/presentation.pptx \
  --type pptx
```

The tool prints a summary and runs the validator automatically:

```
  Slides to render: 4
  Output written: outputs/presentation.pptx
  Validation: PASSED (0 errors, 0 warnings)
```

---

### Tutorial: Converting Markdown to DOCX

Point to any `.md` or `.txt` file and a `.docx` template. The full pipeline parses the markdown structure and injects it into the template body:

```bash
md2office convert \
  --input    report.md \
  --template my-template.docx \
  --output   outputs/report.docx \
  --type docx
```

The DOCX engine preserves all template headers, footers, logos, and styles. Only the body content is replaced.

---

### Tutorial: Exporting Markdown Tables to XLSX

Any markdown file containing tables is automatically mapped to sheets. No template needed:

**Input `data.md`:**

```markdown
# Q1 Sales Report

## Regional Breakdown

| Region | Revenue | Growth |
|--------|---------|--------|
| North  | 142,000 | +12%   |
| South  | 98,500  | +4%    |
| East   | 203,000 | +21%   |
```

**Command:**

```bash
md2office convert \
  --input  data.md \
  --output outputs/q1-report.xlsx \
  --type   xlsx
```

Each `##` section becomes a sheet. Tables become rows. Bullet lists become single-column rows.

---

### Tutorial: Using a Custom Config for a Different Template

If you have a template with different placeholder text than the defaults, create a `my-rules.yaml` that overrides just the `placeholder_map`:

```yaml
placeholder_map:
  section_header:
    title: "CLICK TO EDIT TITLE"
    number: "00"
  bullets:
    title: "SLIDE TITLE"
  key_highlights:
    title: "HIGHLIGHTS"
    subtitle: "subtitle text"
```

Then pass it with `--config`:

```bash
md2office convert \
  --slides-md slides.md \
  --template  corporate-template.pptx \
  --output    output.pptx \
  --config    my-rules.yaml
```

The tool reads the overrides at runtime. No Python changes needed.

---

### Tutorial: Running via Docker (no Python required)

Mount your working directory to `/data` and pass all paths relative to that mount:

```bash
docker run --rm \
  -v $(pwd):/data \
  md2office convert \
  --slides-md /data/slides.md \
  --template  /data/my-template.pptx \
  --output    /data/output.pptx \
  --type pptx
```

For LLM-assisted conversion using a local Ollama model:

```bash
docker compose run --rm md2office convert \
  --input   /data/content.md \
  --template /data/template.pptx \
  --output  /data/output.pptx \
  --type pptx --llm ollama --llm-model mistral
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected: **86 tests pass**.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/guide.md](docs/guide.md) | Full usage, architecture, folder structure, extending the tool |
| [docs/architecture.drawio](docs/architecture.drawio) | System architecture diagram (open with draw.io) |
| [docs/development/changelog.md](docs/development/changelog.md) | All changes with timestamps |
| [docs/development/diagnostics.md](docs/development/diagnostics.md) | Bug fixes and troubleshooting |

---

## Project Structure

```
text2officeprocessor/
├── src/core/
│   ├── models.py              # Domain dataclasses
│   ├── exceptions.py          # Custom exceptions
│   ├── parser/preprocessor.py # md/txt/html → ParsedDocument
│   ├── planner/               # ParsedDocument → SlidePlan/DocPlan/SpreadsheetPlan
│   ├── engines/pptx/          # PPTX engine (SlidePart clone)
│   ├── engines/docx/          # DOCX engine (body injection)
│   ├── engines/xlsx/          # XLSX engine (openpyxl)
│   ├── llm/                   # LLM abstraction layer
│   └── validation/            # Post-render checks
├── src/cli/main.py            # Typer CLI entry point
├── config/                    # YAML configuration
├── templates/                 # Sample templates
├── tests/                     # 38 unit + integration tests
└── docs/                      # Architecture diagram + guide
```

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

Key contribution areas:
- New LLM providers (implement `LLMProvider` base class)
- New output formats (new engine + plan type)
- Draw.io → PNG integration for flowchart slides
- Web UI (Phase 2 roadmap item)
- Additional template types and placeholder maps

---

## License

MIT License — see [LICENSE](LICENSE).

## Author

**Muhammad Danyal (Sage) Khan**
- GitHub: [sage-khan](https://github.com/sage-khan)
- LinkedIn: [sagekhan](https://www.linkedin.com/in/sagekhan)
