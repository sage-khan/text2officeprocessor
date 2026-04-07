# MD2Office — Usage, Architecture & Folder Structure Guide

## Overview

MD2Office is a production-grade Python tool and library that converts plain text formats into professionally formatted office documents using your own branded templates. It takes `.md`, `.txt`, or `.html` as input and produces `.pptx`, `.docx`, or `.xlsx` output — with all template backgrounds, images, fonts, and layouts preserved exactly as designed.

The core principle is **deterministic, template-driven rendering**: every replacement is traceable, every slide is auditable, and no AI model ever writes the final document. An optional LLM layer (Ollama, OpenAI, Claude, Groq, OpenRouter) can normalize and tag content before planning, but the actual document construction is always 100% programmatic.

---

## Installation

### From PyPI (recommended for most users)

```bash
pip install md2office
```

That's it. The `md2office` command is immediately available, and the bundled generic templates are included — no template file needed to get started.

### From source (for development or contribution)

```bash
git clone https://github.com/sage-khan/text2officeprocessor
cd text2officeprocessor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # installs the md2office CLI command in editable mode
```

### Docker

```bash
docker build -t md2office .
```

See the [Docker section](#running-with-docker) for full usage.

---

## Invoking the Tool

### After pip install (PyPI or editable)

```bash
md2office --help
md2office convert --help
```

### As a CLI command (editable install, venv explicit path)

From **any directory** on the system, using the venv binary directly:

```bash
/path/to/text2officeprocessor/.venv/bin/md2office convert \
  --slides-md /path/to/slides.md \
  --template  /path/to/template.pptx \
  --output    /path/to/output.pptx \
  --type pptx
```

Or add the project to your `PATH` permanently and use the included shell wrapper:

```bash
# Add once to ~/.bashrc or ~/.zshrc
export PATH="$PATH:/home/metanet/ProgramFiles/text2officeprocessor"
```

Then from anywhere:

```bash
md2office convert --slides-md section-02-slides.md \
  --template ec-council-sections.pptx \
  --output section-02.pptx --type pptx

md2office analyze my-template.pptx
```

### Via Docker (no Python needed on host)

```bash
docker run --rm \
  -v /path/to/your/files:/data \
  md2office convert \
  --slides-md /data/slides.md \
  --template  /data/template.pptx \
  --output    /data/output.pptx \
  --type pptx
```

---

## Quick Start Examples

### Zero-config — no template needed

After install, the bundled `generic-slides.pptx` is used automatically when you omit `--template`:

```bash
md2office convert \
  --slides-md slides.md \
  --output    outputs/presentation.pptx
```

See what templates are bundled:

```bash
md2office templates
```

### PPTX from pre-authored slides markdown

Use your own branded template by passing `--template`:

```bash
md2office convert \
  --slides-md slides.md \
  --template  template.pptx \
  --output    outputs/presentation.pptx \
  --type pptx
```

### PPTX from raw markdown (full pipeline)

MD2Office parses the markdown, normalizes it with rule-based heuristics (or an LLM), and maps content to slides automatically:

```bash
md2office convert \
  --input    content.md \
  --template template.pptx \
  --output   output.pptx \
  --type pptx
```

### PPTX with a custom rules config

Pass `--config` to override placeholder strings and validation thresholds for a specific template:

```bash
md2office convert \
  --slides-md slides.md \
  --template  template.pptx \
  --output    output.pptx \
  --config    my-template-rules.yaml
```

### PPTX with LLM normalization

Add `--llm` and `--llm-model` to use an LLM for semantic tagging before planning:

```bash
md2office convert \
  --input     content.md \
  --template  template.pptx \
  --output    output.pptx \
  --type pptx \
  --llm ollama \
  --llm-model mistral
```

### DOCX output

```bash
md2office convert \
  --input    content.md \
  --template template.docx \
  --output   output.docx \
  --type docx
```

### XLSX output

No template needed. Tables in the markdown become sheets:

```bash
md2office convert \
  --input  report.md \
  --output report.xlsx \
  --type xlsx
```

### Analyze a template before authoring

Before writing a `slides.md` for a new template, run `analyze` to discover the exact placeholder text strings in every shape:

```bash
md2office analyze path/to/template.pptx
```

This prints every slide, shape, paragraph, and run — giving you the exact strings to use in `- placeholder: "old" → "new"` lines.

---

## Embedding Draw.io Diagrams

Any slide in your `slides.md` can include a draw.io diagram (or a plain PNG/JPG). The diagram is exported to a temporary PNG and embedded centred on the slide with a 0.5" margin, preserving aspect ratio.

### In slides.md

```markdown
## SLIDE 3 — template_index: 2 (Single Point)
- placeholder: "SINGLE POINT SLIDE" → "System Architecture"
- diagram: "diagrams/architecture.drawio"
```

Paths are resolved relative to the working directory where `md2office convert` is run.

### Supported diagram formats

| Format | Handling |
|--------|----------|
| `.drawio` | Exported via `drawio --export --format png` (headless: `xvfb-run` used automatically) |
| `.png` / `.jpg` / `.jpeg` | Embedded directly — no conversion |

### Standalone export command

Export a `.drawio` file to PNG without generating a presentation:

```bash
md2office drawio-export diagrams/architecture.drawio
md2office drawio-export diagrams/architecture.drawio --output outputs/architecture.png --scale 3
md2office drawio-export diagrams/multi-page.drawio --all-pages --output outputs/
md2office drawio-export diagrams/flow.drawio --page 2 --transparent
```

### Requirements

The `drawio` desktop CLI must be installed:
- **Linux/Ubuntu:** `sudo apt install drawio` or download the AppImage from [drawio-desktop releases](https://github.com/jgraph/drawio-desktop/releases)
- **Docker:** use the `docker-compose.yml` with the `drawio` sidecar image

If `drawio` is unavailable at render time, the slide is rendered normally with only a warning log — the missing diagram is a soft failure, not an abort.

---

## LLM Semantic Validation

After any render, you can run an optional LLM-powered coherence check on the output. This is in addition to the always-on programmatic checks.

```bash
md2office convert \
  --slides-md slides.md \
  --output output.pptx \
  --llm ollama --llm-model mistral \
  --llm-validate
```

### What the LLM checks

| Issue type | Description |
|---|---|
| `TRUNCATED` | Text run appears cut off mid-sentence or mid-word |
| `GARBLED` | Incoherent or scrambled text |
| `PLACEHOLDER_LEAK` | Unreplaced template text still visible |
| `MISMATCH` | Slide/section content does not match its heading |
| `EMPTY_SECTION` | Slide or section has a title but no body |

### Behaviour

- Requires `--llm` to be configured. Without `--llm`, the flag is silently ignored (with a `[WARN]` note).
- Content is truncated to 8 000 characters before being sent to the LLM.
- All failures (provider unavailable, malformed response, parse error) return an empty result — the document is **always saved**.
- Works with all providers: `ollama`, `openai`, `claude`, `openrouter`, `groq`.
- Also available on `md2office batch --llm-validate`.

### Example output

```
  Validation: PASSED (no issues)
  LLM semantic validation:
  Validation: PASSED with 1 issue(s)
    [WARNING] Slide 4 / title: [PLACEHOLDER_LEAK] "Section Name Here" still present
```

---

## Batch Converting a Directory

Convert every markdown, text, or HTML file in a folder in one command. Output files are named after their source file, with the output extension appended:

```bash
md2office batch \
  --input-dir ./content/ \
  --output-dir ./outputs/ \
  --type xlsx
```

Output:

```
Batch: 4 file(s) → XLSX in 'outputs/'

  [1/4] report-q1.md → report-q1.xlsx
  [2/4] report-q2.md → report-q2.xlsx
  [3/4] report-q3.md → report-q3.xlsx
  [4/4] report-q4.md → report-q4.xlsx

==================================================
Batch complete: 4/4 succeeded, 0 failed.
```

**Filter to specific files** with `--pattern`:

```bash
md2office batch \
  --input-dir ./slides/ \
  --output-dir ./outputs/ \
  --type pptx \
  --template corporate.pptx \
  --pattern "section-*.md"
```

**Continue on error** (default) or **stop on first failure** with `--fail-fast`:

```bash
md2office batch \
  --input-dir ./content/ \
  --output-dir ./outputs/ \
  --type pptx \
  --fail-fast
```

If any file fails, its error is printed inline and the final summary lists all failures. The exit code is non-zero if any file failed.

---

## Slides Markdown Format

The primary PPTX workflow uses a structured markdown file that maps content explicitly to template slide types. This format bypasses the LLM normalization step entirely and gives you full, deterministic control over every slide.

```markdown
## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Your Section Title"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Key Concepts"
- bullets:
  - "First bullet point"
  - "Second bullet point"
  - "Third bullet point"

---

## SLIDE 3 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "What You Will Learn"
- placeholder: "Enter your subhead line here" → "4 core topic areas"
- card_1_title: "Topic One"
- card_1_body: "Description of topic one"
- card_2_title: "Topic Two"
- card_2_body: "Description of topic two"
- card_3_title: "Topic Three"
- card_3_body: "Description of topic three"
- card_4_title: "Topic Four"
- card_4_body: "Description of topic four"

---

## SLIDE 4 — template_index: 11 (Excellence Grid — 3 items)
- placeholder: "EXCELLENCE IN THE" → "Course Highlights"
- item_01_title: "Evidence-Based"
- item_01_body: "All claims backed by research."
- item_02_title: "Practical"
- item_02_body: "Hands-on labs in every module."
- item_03_title: "Comprehensive"
- item_03_body: "Covers the full audit lifecycle."
```

### Parsing rules

| Pattern | Meaning |
|---|---|
| `## SLIDE N — template_index: N (Type)` | Slide definition header |
| `- placeholder: "old" → "new"` | Single-line text replacement |
| `- bullets:` followed by `  - "text"` | Bullet injection |
| `- card_N_title: "..."` | Key Highlights card title |
| `- card_N_body: "..."` | Key Highlights card body |
| `- item_N_title: "..."` | Features/Benefits item title |
| `- item_0N_title: "..."` | Excellence Grid item title |
| `---` | Slide separator (resets bullet mode) |

The `template_index` corresponds to the zero-based position of the slide in the template file's slide bank. Use `md2office analyze` to discover which index maps to which slide layout.

---

## Architecture

The pipeline has six stages. Each stage has a single responsibility and a well-defined interface:

```
Input (.md / .txt / .html)
         │
         ▼
  InputPreprocessor
  (normalize encoding, parse headings/lists/tables → ParsedDocument)
         │
         ▼
  LLMNormalizer  ←── optional; falls back to rule-based heuristics
  (semantic tagging → [(SlideIntent, SlideContent)])
         │
  ┌──────┤  shortcut: --slides-md bypasses both stages above
  │      ▼
  │  ContentPlanner
  │  (maps to SlidePlan / DocPlan / SpreadsheetPlan)
  │      │
  │ ┌────┴──────────────────┐
  │ ▼                       ▼                    ▼
  │ PPTXEngine          DOCXEngine           XLSXEngine
  │ (SlidePart clone)   (body inject)        (openpyxl map)
  │      │                   │                    │
  │      └───────────────────┴────────────────────┘
  │                          │
  │                          ▼
  │               ProgrammaticValidator
  │               (artifacts, placeholders, size heuristics)
  │                          │
  └──────────────────────────▼
                    Output (.pptx / .docx / .xlsx)
```

### Non-negotiable architecture rules

These rules exist because violating them causes silent data loss or corrupt output:

1. **PPTX must use SlidePart cloning** — preserves backgrounds, images, and complex layouts. `add_slide()` alone and `deepcopy(slide)` both lose relationships.
2. **DOCX must iterate `source.element.body` children in order** — tables must stay inline with their surrounding paragraphs.
3. **LLM scope is strictly normalization** — the LLM may tag and classify content, but never writes runs, paragraphs, or shapes.
4. **No layout mutation** — shapes are never moved, resized, or rebuilt. Only run-level text is touched.
5. **No markdown artifacts** — `**`, `__`, `---` are stripped from all runs before saving.
6. **Templates are sacred** — clone/inject only, never modify the source template file.

---

## Text Overflow Handling

When injected content is longer than a shape's bounding box allows, MD2Office automatically reduces the font size to keep everything within bounds. This runs as a post-injection step on every slide, after replacements, bullets, and structured items have all been applied.

**How it works:**

The engine estimates overflow by comparing the total character count of a shape's text against its bounding box capacity (derived from shape width, height, and average font size). If overflow is detected, all runs in the shape have their font sizes reduced by 2pt per iteration until either the content fits or the configured minimum font size is reached.

- **Step size:** 2pt per iteration
- **Minimum font size:** 8pt (configurable). Below this, a warning is logged instead of further shrinking.
- **Shapes with `MSO_AUTO_SIZE`** already set by the template are skipped — the template handles them natively.
- **Group shapes** are recursed into automatically.

These thresholds are configurable in `config/default_rules.yaml`:

```yaml
text_overflow:
  enabled: true
  min_font_size_pt: 8
  step_pt: 2
  max_iterations: 20
```

If a shape still overflows at 8pt, the log will emit: `"Shape 'X': text still overflows at minimum font size 8pt — consider shortening the content."` This is the signal to trim the source content rather than push the font size lower.

---

## Folder Structure

```
text2officeprocessor/
├── src/
│   ├── core/
│   │   ├── models.py              # Domain dataclasses: ParsedDocument, SlidePlan, etc.
│   │   ├── exceptions.py          # Custom exceptions
│   │   ├── parser/
│   │   │   └── preprocessor.py   # InputPreprocessor — md/txt/html → ParsedDocument
│   │   ├── planner/
│   │   │   └── content_planner.py # ContentPlanner — ParsedDocument → SlidePlan/DocPlan/SpreadsheetPlan
│   │   ├── engines/
│   │   │   ├── pptx/
│   │   │   │   └── engine.py     # PPTXEngine — SlidePart clone + inject + overflow shrink
│   │   │   ├── docx/
│   │   │   │   └── engine.py     # DOCXEngine — template body injection
│   │   │   └── xlsx/
│   │   │       └── engine.py     # XLSXEngine — openpyxl structured mapping
│   │   ├── llm/
│   │   │   ├── base.py           # LLMProvider abstract base class
│   │   │   ├── providers.py      # OllamaProvider, OpenAIProvider, ClaudeProvider, etc.
│   │   │   └── normalizer.py     # LLMNormalizer — ParsedDocument → [(SlideIntent, SlideContent)]
│   │   └── validation/
│   │       └── validator.py      # ProgrammaticValidator — post-render checks
│   └── cli/
│       └── main.py               # Typer CLI — md2office convert / analyze
├── config/
│   ├── default_rules.yaml        # Formatting, overflow, and validation defaults
│   └── llm_config.yaml           # LLM provider configuration
├── templates/                    # Bundled sample templates
├── tests/
│   ├── data/                     # Test input files
│   ├── templates/                # Test template fixtures
│   ├── test_preprocessor.py
│   ├── test_planner.py
│   ├── test_pptx_engine.py
│   ├── test_docx_engine.py
│   └── test_xlsx_engine.py
├── src/
│   └── data/                     # Bundled package data (included in PyPI wheel)
│       ├── templates/
│       │   ├── generic-slides.pptx
│       │   └── generic-document.docx
│       └── config/
│           ├── default_rules.yaml
│           └── llm_config.yaml
├── docs/
│   ├── guide.md                  # This file
│   ├── architecture.drawio       # System architecture diagram (draw.io)
│   └── development/
│       ├── changelog.md
│       └── diagnostics.md
├── scripts/
│   └── create_bundled_templates.py  # Regenerate bundled templates
├── Dockerfile                    # Standard Docker image
├── docker-compose.yml            # Compose for local dev + Ollama LLM
├── md2office                     # Shell wrapper (add to PATH for system-wide use)
├── outputs/                      # Default output directory (gitignored)
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## LLM Provider Setup

LLM is entirely optional. Without it, the tool uses rule-based heuristics and works fully offline.

| Provider | Flag | Required Env Var | Default Model |
|---|---|---|---|
| Ollama (local) | `--llm ollama` | None | `mistral` |
| OpenAI | `--llm openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Claude | `--llm claude` | `ANTHROPIC_API_KEY` | `claude-3-haiku-20240307` |
| OpenRouter | `--llm openrouter` | `OPENROUTER_API_KEY` | varies |
| Groq | `--llm groq` | `GROQ_API_KEY` | `llama3-8b-8192` |

**Never hardcode API keys.** Pass them as environment variables:

```bash
export OPENAI_API_KEY="sk-..."
md2office convert --input content.md --template t.pptx --output out.pptx \
  --type pptx --llm openai
```

When using Docker, pass keys via `--env` or an `.env` file:

```bash
docker run --rm --env-file .env \
  -v /path/to/files:/data \
  md2office convert --input /data/content.md --template /data/t.pptx \
  --output /data/out.pptx --type pptx --llm openai
```

---

## Running with Docker

### Build

```bash
docker build -t md2office .
```

### Convert a file

Mount your working directory to `/data` inside the container:

```bash
docker run --rm \
  -v $(pwd):/data \
  md2office convert \
  --slides-md /data/slides.md \
  --template  /data/template.pptx \
  --output    /data/output.pptx \
  --type pptx
```

### Analyze a template

```bash
docker run --rm \
  -v $(pwd):/data \
  md2office analyze /data/template.pptx
```

### With Ollama (local LLM, no API key needed)

Use `docker-compose.yml` which starts both md2office and an Ollama sidecar:

```bash
docker compose up -d ollama
docker compose run --rm md2office convert \
  --input /data/content.md \
  --template /data/template.pptx \
  --output /data/output.pptx \
  --type pptx --llm ollama --llm-model mistral
```

---

## Output Verification

After rendering a PPTX, you can visually verify every slide by converting to PDF and extracting slide images:

```bash
# Convert to PDF
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.pptx

# Extract slide images at 150 DPI
pdftoppm -png -r 150 /tmp/verify/output.pdf /tmp/slides/slide

# Review
ls -lh /tmp/slides/
```

### File size heuristics (PPTX)

The file size of individual slides is a reliable indicator of whether template backgrounds were preserved correctly by the SlidePart cloning step:

| Size per slide | Meaning |
|---|---|
| < 50 KB | Missing background — SlidePart cloning likely broken |
| 50–150 KB | Simple slide (no background image) — expected for plain layouts |
| 200–500 KB | Full background image preserved — correct |

If slides are unexpectedly small, check that the template is being loaded from the correct path and that `duplicate_slide()` in the engine is not falling back to index 0 unexpectedly.

---

## Extending MD2Office

### Adding a new LLM provider

1. Create a class in `src/core/llm/providers.py` extending `LLMProvider`
2. Implement `generate(self, prompt: str) -> str` and `is_available(self) -> bool`
3. Register it in the `build_provider()` factory function
4. Add tests in `tests/test_llm_<provider>.py`
5. Update `config/llm_config.yaml` with the default model

### Adding a new template type

1. Run `md2office analyze` on the new template to identify placeholder strings and layout positions
2. Update `DEFAULT_TEMPLATE_MAP` in `content_planner.py` with the new `SlideIntent → (template_index, type_name)` mapping
3. If the slide uses structured items (cards, grids, icons), add injection logic in `apply_items()` in `pptx/engine.py`

### Adding a new output engine

1. Create `src/core/engines/<format>/engine.py` with a class implementing `render(plan, output_path) -> Path`
2. Add the format to the `OutputFormat` enum in `src/core/models.py`
3. Wire it in `src/cli/main.py` under the appropriate `--type` branch

---

## Custom Configuration

All variable behaviour — placeholder strings, font size limits, validation thresholds — is driven by a YAML config file. The default is `config/default_rules.yaml`. Pass `--config path/to/rules.yaml` at the CLI to use a different one for a specific project.

The most important customisable section is `placeholder_map`. If your template uses different placeholder text strings, override them:

```yaml
placeholder_map:
  section_header:
    title: "Your Template Title Placeholder"
    number: "Your Number Placeholder"
  bullets:
    title: "Your Slide Title Placeholder"
  stats:
    title: "Your Big Number Placeholder"
    body: "Your Description Placeholder"
```

All other fields (font overflow limits, validation strictness, header colour, etc.) follow the same pattern — copy `config/default_rules.yaml` and override only the keys you need.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected: **38 tests pass** across the preprocessor, planner, all three engines, and the validator.

To run a specific module:

```bash
python -m pytest tests/test_pptx_engine.py -v
```

---

## License

MIT License — see `LICENSE` file.

## Author

Muhammad Danyal (Sage) Khan — [GitHub](https://github.com/sage-khan) — [LinkedIn](https://www.linkedin.com/in/sagekhan)
