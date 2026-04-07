# MD2Office — Intelligent Document Converter

> Convert **Markdown / Text / HTML** to **PPTX, DOCX, and XLSX** using template-driven deterministic rendering with optional LLM normalization.

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
git clone https://github.com/sage-khan/md2office
cd md2office
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Generate a PPTX from pre-authored slides markdown

```bash
md2office convert \
  --slides-md slides.md \
  --template template.pptx \
  --output outputs/presentation.pptx \
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

### Analyze a template before authoring

```bash
md2office analyze path/to/template.pptx
```

---

## Slides Markdown Format

The primary PPTX workflow uses a structured markdown format:

```markdown
## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Introduction to AI Auditing"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Why It Matters"
- bullets:
  - "COMPAS: 45% false positive rate for Black defendants vs 23% for white"
  - "EU AI Act: up to 35M euros or 7% global revenue for non-compliance"

---

## SLIDE 3 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "What You Will Learn"
- card_1_title: "Foundations"
- card_1_body: "ML fundamentals and auditing frameworks"
- card_2_title: "Legal & Compliance"
- card_2_body: "GDPR, EU AI Act, NIST AI RMF"
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
python -m src.cli.main convert --input content.md --template t.pptx \
  --output out.pptx --type pptx --llm ollama --llm-model mistral
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected: **38 tests pass**.

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
