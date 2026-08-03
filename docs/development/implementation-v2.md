# Text2OfficeProcessor v2 — Implementation Plan

## Date: 2026-04-13

## Status: In Progress

---

## 1. Problem Statement

Text2OfficeProcessor v0.x delivers functional MD/TXT/HTML → PPTX/DOCX/XLSX conversion using
template placeholder matching and rule-based content planning. However, the approach
has structural limitations that prevent production-grade output quality:

- **One-way only** — no Office → Markdown extraction for round-trip workflows
- **Fragile placeholder matching** — text-replace against literal template strings
- **No style awareness** — cannot extract or re-apply font/color/spacing from templates
- **Template-locked** — switching templates requires rewriting the placeholder map

These limitations were identified by studying two mature open-source tools:
**edgemint** (Raphael Mansuy, Apache 2.0) and **opendataloader-pdf** (Apache 2.0).

---

## 2. Reference Architecture Study

### 2.1 Edgemint (DOCX specialist)

Repository: `github.com/raphaelmansuy/edgemint`

**Core idea**: Separate visual identity from content. Extract complete style state from
a `.docx` template into a portable `styles.json`, then apply that identity to any
Markdown content to regenerate pixel-perfect branded documents.

**Key modules studied:**

| Module | Purpose | Takeaway for Text2OfficeProcessor |
|--------|---------|----------------------|
| `extract/document.py` | Reads styles.xml, theme1.xml, numbering.xml from DOCX ZIP | We need equivalent PPTX/DOCX style extraction |
| `schema/models.py` | Pydantic models: `StyleSheet`, `Style`, `FontProperties`, `ParagraphFormat`, `ThemeInfo` | We should model extracted styles as structured JSON, not just YAML placeholder maps |
| `apply.py` | Generates reference.docx from StyleSheet, runs Pandoc, post-processes | Pandoc + reference.docx is a proven DOCX path |
| `markdown.py` | Parses `{custom-style="..."}` fenced divs and bracketed spans | Style-aware Markdown annotations are valuable for power users |
| `cli.py` | `extract-styles`, `apply-styles`, `extract`, `diff`, `validate`, `info` | Template analysis CLI commands are essential for usability |

**Architecture pattern:**

```
Template (.docx)                Content (.md)
       |                              |
       v                              |
  extract-styles                      |
       |                              |
       v                              v
  styles.json  ------>  apply-styles ------>  output.docx
```

### 2.2 OpenDataLoader-PDF (extraction specialist)

Repository: `github.com/opendataloader-project/opendataloader-pdf`

**Core idea**: Hybrid processing — fast deterministic local mode for simple content,
AI backend for complex pages. Bounding-box-aware layout analysis. Multi-format output:
Markdown, JSON (with coordinates), HTML, Tagged PDF.

**Takeaway for Text2OfficeProcessor:**

| Concept | How it applies |
|---------|---------------|
| Hybrid AI mode | Route simple sections through rules, complex sections through LLM |
| Layout analysis with coordinates | For PPTX extraction, preserve slide geometry |
| Benchmark-driven quality | We need accuracy metrics for conversion quality |
| Multi-format output | Already supported (PPTX/DOCX/XLSX) |

---

## 3. Implementation Plan

### Phase 0 — Foundation (this PR)

#### P0a: Style Extraction Module

**New module:** `src/core/extraction/style_extractor.py`

Extract complete visual identity from DOCX and PPTX templates into a structured
JSON format (`StyleSheet`), enabling template-aware generation.

**DOCX style extraction** (inspired by edgemint `extract/document.py`):
- Parse `styles.xml` → extract paragraph and character style definitions
- Parse `theme1.xml` → extract theme fonts and colors
- Parse `numbering.xml` → extract list numbering definitions
- Read section properties (page size, margins, orientation)
- Read headers/footers as raw XML
- Output: `styles.json` with full visual identity

**PPTX style extraction** (new, no edgemint equivalent):
- Parse slide layouts → extract placeholder positions, sizes, types
- Parse slideMaster → extract theme colors, fonts, backgrounds
- Map slide layout indices to placeholder schema
- Output: `pptx_styles.json` with layout geometry

**Data models** (`src/core/extraction/models.py`):

```python
@dataclass
class FontProperties:
    name: str | None = None
    size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    color: str | None = None  # hex

@dataclass
class ParagraphFormat:
    alignment: str | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    line_spacing: float | None = None
    indent_left_pt: float | None = None

@dataclass
class DocxStyle:
    style_id: str
    name: str
    style_type: str  # paragraph | character | table
    based_on: str | None = None
    font: FontProperties | None = None
    paragraph_format: ParagraphFormat | None = None

@dataclass
class PptxSlideLayout:
    index: int
    name: str
    placeholders: list[PlaceholderInfo]

@dataclass
class PlaceholderInfo:
    idx: int
    type: str  # title | body | subtitle | picture
    left_pt: float
    top_pt: float
    width_pt: float
    height_pt: float
    font: FontProperties | None = None

@dataclass
class ExtractedStyleSheet:
    format: str  # "docx" | "pptx"
    source_file: str
    extracted_at: str
    tool_version: str
    styles: list[DocxStyle] | None = None
    slide_layouts: list[PptxSlideLayout] | None = None
    theme_colors: dict[str, str] = field(default_factory=dict)
    theme_fonts: dict[str, str] = field(default_factory=dict)
```

#### P0b: Office → Markdown Extraction (Reverse Pipeline)

**New module:** `src/core/extraction/content_extractor.py`

Extract content from Office files back into Markdown, enabling round-trip editing.

**DOCX → Markdown:**
- Use Pandoc when available (best quality, preserves custom styles as fenced divs)
- Direct fallback with python-docx: iterate paragraphs → Markdown headings/body/lists
- Extract embedded images to `media/` directory

**PPTX → Markdown:**
- Extract each slide into the canonical `## SLIDE N` format
- Read placeholder text, notes, and images
- Preserve slide layout index for re-generation

**XLSX → Markdown:**
- Each sheet → section heading
- Data rows → Markdown tables

**CLI commands:**

```bash
text2officeprocessor extract report.docx -o project/
# → project/content.md
# → project/styles.json
# → project/media/

text2officeprocessor extract slides.pptx -o project/
# → project/slides.md  (canonical slides markdown format)
# → project/pptx_styles.json
# → project/media/

text2officeprocessor extract data.xlsx -o project/
# → project/content.md  (markdown tables)
```

### Phase 1 — Enhanced Generation

#### P1a: Pandoc Integration for DOCX (proven method from edgemint)

When Pandoc is available, use the Pandoc pipeline for DOCX generation instead of
direct python-docx injection. This gives superior style fidelity.

**Flow:**
1. Extract styles from template → `styles.json`
2. Build a `reference.docx` containing all style definitions
3. Run Pandoc: `md → docx` using the reference document
4. Post-process: sync headers/footers, inject images

**Fallback:** When Pandoc is not installed, use current python-docx engine (unchanged).

#### P1b: Template Analysis CLI

New subcommands for template introspection:

```bash
text2officeprocessor analyze-template template.pptx
# Shows: slide count, layout names, placeholder positions, fonts

text2officeprocessor extract-styles template.docx -o styles.json
# Extracts full visual identity to JSON

text2officeprocessor diff-styles old.json new.json
# Compares two extracted style sheets
```

### Phase 2 — Advanced Features (future)

- Style-aware Markdown input (`{custom-style="..."}` fenced divs)
- Hybrid AI mode: route complex sections to LLM, simple ones to rules
- Visual regression testing with LibreOffice headless rendering
- Accessibility tagging for PDF output

---

## 4. Directory Structure (additions)

```
src/core/
  extraction/              # NEW — reverse pipeline
    __init__.py
    models.py              # ExtractedStyleSheet, FontProperties, etc.
    style_extractor.py     # DOCX/PPTX → styles.json
    content_extractor.py   # DOCX/PPTX/XLSX → content.md
tests/
  test_style_extractor.py  # NEW
  test_content_extractor.py # NEW
```

---

## 5. Dependencies

| Package | Purpose | Status |
|---------|---------|--------|
| `python-docx` | DOCX read/write | Already present |
| `python-pptx` | PPTX read/write | Already present |
| `openpyxl` | XLSX read/write | Already present |
| `lxml` | XML parsing for style extraction | Already present |
| `pydantic` | Structured style models (optional, can use dataclasses) | Not yet added |

Pandoc is an **optional** external dependency (not pip-installable). When absent, the
system falls back to direct python-docx/pptx extraction and generation.

---

## 6. Compatibility

All changes are **backward compatible**. Existing commands and APIs continue to work.
New functionality is additive:
- New `extract` command does not affect `convert`
- New `extract-styles` command is standalone
- Pandoc integration is opt-in (auto-detected)
- Style extraction models are independent of the existing pipeline
