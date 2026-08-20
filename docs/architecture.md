# Architecture

How text2officeprocessor is built: the extraction/generation pipeline, why it
looks the way it does, and where each piece lives. For "what changed and
when," see [`docs/changelog.md`](changelog.md); for "what's new in a given
release," see [`docs/feature.md`](feature.md).

---

## 1. Design goals

- **One-way generation is not enough for production use.** A tool that only
  writes PPTX/DOCX/XLSX can't be round-tripped, diffed, or re-styled once a
  template changes. text2officeprocessor supports both directions: content
  generation (Markdown/TXT/HTML → Office) and structural extraction (Office
  → Markdown + a style manifest).
- **Never rebuild a template from scratch.** Every generation engine clones
  the template at the XML/part level and injects content at the run level —
  see [`docs/guide.md`](guide.md) and the `office-template-cloning`-style
  rules this library's proven methods were extracted from. `add_slide()`,
  `deepcopy(slide)`, and Pandoc's `--reference-doc` for PPTX are all
  explicitly avoided because each one loses backgrounds, breaks picture
  placeholders, or corrupts package relationships.
- **LLM involvement is scoped to labeling, never to layout.** Wherever an
  LLM is used (content normalization, spreadsheet reorganization, the
  layout-manifest classification pass — §5 below), it only ever picks among
  a fixed set of proven, human-reviewed recipes. It never writes XML, moves
  a shape, or decides pixel geometry. This keeps a bad LLM guess bounded to
  "picked the wrong but still-safe recipe," never "corrupted the file."

This design was informed by studying two mature open-source tools:
**edgemint** (Raphael Mansuy, Apache 2.0) for DOCX style-extraction
patterns, and **opendataloader-pdf** (Apache 2.0) for hybrid
deterministic/AI processing and bounding-box-aware layout analysis.

---

## 2. Pipeline overview

```
Content generation:
  .md / .txt / .html  →  InputPreprocessor  →  LLMNormalizer (optional)
                       →  ContentPlanner     →  PPTXEngine / DOCXEngine / XLSXEngine
                       →  .pptx / .docx / .xlsx

Structural extraction (reverse pipeline):
  .pptx / .docx / .xlsx  →  style_extractor.py   →  ExtractedStyleSheet (styles.json)
                          →  content_extractor.py →  content.md + media/
```

| Stage | Module | Responsibility |
|-------|--------|-----------------|
| Parse | `src/core/parser/preprocessor.py` | Encoding-safe `.md`/`.txt`/`.html` → `ParsedDocument` (DOM-aware for HTML) |
| Normalize | `src/core/llm/normalizer.py` | Semantic tagging (`SlideIntent`, content shape) — rule-based fallback when no LLM configured |
| Plan | `src/core/planner/content_planner.py` | `(intent, content)` pairs → `SlideDefinition`/`DocPlan`/`SpreadsheetPlan`; also parses the canonical `## SLIDE N — template_index: N` markdown format directly |
| Render — PPTX | `src/core/engines/pptx/engine.py` | SlidePart clone + run-level inject; `image_injector.py` for template-aware picture-slot fill |
| Render — DOCX | `src/core/engines/docx/engine.py` | Template body replacement (in-order paragraph/table iteration) or Pandoc `--reference-doc`, with post-processing |
| Render — XLSX | `src/core/engines/xlsx/engine.py` | Direct `openpyxl` construction — no template to preserve, so no cloning risk |
| Validate | `src/core/validation/validator.py` | Programmatic checks (artifacts, placeholders, file size) + optional LLM semantic pass |
| Extract | `src/core/extraction/` | Reverse pipeline — see §4 |
| Analyze | `src/core/analysis/` | Layout manifests — see §5 |

---

## 3. Generation engines

### 3.1 PPTX — SlidePart clone + inject

`duplicate_slide()` deep-copies a template bank slide's XML element and
re-inserts every one of its relationships under its **original** rId (never
`rels.get_or_add()`, which mints fresh rIds and silently breaks any
`r:embed` reference already hardcoded in the cloned XML — this was a real,
non-deterministic defect, fixed in 0.4.2). Content is then injected with a
3-layer text-replacement strategy (curly-quote normalization, single-run
match, cross-run match) that never touches `text_frame.clear()` or
`text_frame.text = ...`, both of which destroy run-level formatting.

Structured content (bullets, grid cards, images) goes through dedicated
helpers rather than generic text replace:
- `set_bullets()` fills a bullet box's paragraph slots, **removing** any
  slot beyond the supplied bullet count (not blanking it — an empty `<a:p>`
  can still carry an inherited bullet-glyph definition that some renderers
  draw anyway) and normalizing every filled paragraph's indent/bullet-glyph
  to paragraph 0's values, since template paragraph slots are not
  uniformly styled in the underlying XML.
- `apply_items()` / `_remove_unreplaced_item_placeholders()` fill grid/card
  slides (Key Highlights, Features, Benefits, Excellence Grid) and remove
  any slot with no matching content — supplying fewer items than a
  template has card slots is normal, not an error, so the unmatched slot's
  shape is removed rather than left showing template placeholder text (or,
  on this library's own bundled template, the literal internal key name).
- `image_injector.find_image_slot()` / `inject_template_image()` locate a
  slide's actual picture slot (native placeholder or a labelled
  text-stand-in) and crop the source image to the slot's aspect ratio
  before embedding, so the template's proportions are preserved exactly —
  never `add_picture()` at guessed coordinates.
- `fit_text_to_shape()` runs on every rendered slide, shrinking any
  overflowing shape's font in 2pt steps, capped at 6pt below that run's own
  template size (never down to one global floor regardless of the
  template's original size). This applies uniformly to every shape,
  including fixed (`noAutofit`) boxes like Callout/Stats — there's no
  separate carve-out needed for those.

### 3.2 DOCX — template body replacement or Pandoc

Two paths, selected automatically (Pandoc when available, python-docx
fallback otherwise) or forced via `DOCXEngine(use_pandoc=True|False)`:
- **python-docx path**: clears the template body except paragraphs
  containing an image (logo, decorative lines), then injects each
  section's content blocks **in the order they appear** — paragraph, list,
  table, paragraph, ... — by iterating the section's own content list and
  calling the matching `add_*` method per block, never collecting all
  paragraphs first and all tables second (which would dump every table at
  the end of the document, out of place). Verified by direct render — see
  `docs/diagnostics.md`.
- **Pandoc path**: `md → docx` via `--reference-doc`, then `_harden_tables()`
  post-processes cell borders/formatting Pandoc's own conversion doesn't
  set.

### 3.3 XLSX — direct construction

No template-cloning risk exists for XLSX (no fragile background/layout to
preserve), so sheets are built directly with `openpyxl`'s high-level API.
When an LLM is configured, `SpreadsheetReorganizer`
(`src/core/planner/spreadsheet_reorganizer.py`) consolidates a naive
one-sheet-per-markdown-section layout into logical archetypes (`dashboard`,
`breakdown`, `timeline`, `comparison`, `matrix`, `raw`) before generation;
a rule-based fallback (KPI regex extraction, table fingerprinting) covers
the no-LLM case.

---

## 4. Extraction pipeline (Office → Markdown + styles)

`src/core/extraction/` — added to support round-trip workflows (edit
generated content and rebuild without losing template identity):

- `style_extractor.py` → `ExtractedStyleSheet`: DOCX styles.xml, theme,
  numbering, section properties; PPTX slide layouts, placeholder geometry,
  theme colors/fonts. Pure structural data, no semantic labeling.
- `content_extractor.py` → Markdown: DOCX via Pandoc (preferred) or
  python-docx fallback; PPTX into the canonical
  `## SLIDE N — template_index: N` format (round-trip ready — the same
  format `ContentPlanner.parse_slides_markdown` consumes); XLSX into
  Markdown tables, one section per sheet. Embedded media extracted
  alongside.
- CLI: `extract-styles`, `extract`, `analyze-template`, `diff-styles`.

---

## 5. Layout manifests (`src/core/analysis/`)

Static template mapping (`ContentPlanner.DEFAULT_TEMPLATE_MAP`) only
covers the one bundled 13-slide PPTX bank. Any other template requires
hand-writing a slides-md file with exact `template_index` values, because
nothing inspects an unfamiliar template and reports which slide fits "four
stats," whether a slot takes an image, or whether a table will fit.

A **layout manifest** (`analyze-template <file> --manifest out.json`) is
the answer: a per-template JSON file (`TemplateManifest`,
`src/core/analysis/models.py`) the planner and an LLM can both read,
generated in two passes:

1. **Structural pass (deterministic, `src/core/analysis/structural.py`)** —
   the same shape-inspection heuristics the plain `analyze` CLI command
   prints (`classify_pptx_slide_structure()` — one shared implementation,
   not a duplicate) enumerate each slide's shapes, groupings, and a
   best-guess `content_affinity`; the same pass over a DOCX template
   (`build_docx_section_manifests()`) reports which heading styles exist
   and whether the template supports tables/images at all. This is ground
   truth and always wins over an LLM guess for anything measurable.
2. **Classification pass (LLM, optional, `src/core/analysis/manifest.py`)**
   — for PPTX only (a DOCX template has no discrete slide bank to
   classify), refines each slide's `content_affinity` and adds a one-line
   `notes` summary. The manifest is **advisory metadata, never executable
   logic**: `_merge_slide()` only ever overlays those two semantic fields
   onto the structural result — it never touches `slots` at all, so an LLM
   response can never change which `injection_recipe` a slot is labelled
   with, let alone select a value outside the fixed `INJECTION_RECIPES`
   enum. A provider failure (unreachable, malformed JSON) is caught and
   silently falls back to the structural-only manifest — classification is
   always optional, never a hard dependency.

XLSX intentionally has no manifest generator: `XLSXEngine` builds sheets
directly with no template to clone (§3.3), so there is no injection-safety
contract for a manifest to describe; `get_or_generate_manifest()` raises a
clear `ValueError` for `.xlsx` rather than pretending to support it.

Manifests are cached next to the template as
`<template_stem>.layout-manifest.json` and regenerated only when the
template's mtime is newer than the cached manifest's (`get_or_generate_manifest()`,
`force=True` to bypass). `ContentPlanner(manifest=...)` consults
`TemplateManifest.best_slide_for()` per slide's intent, falling back to
the static `DEFAULT_TEMPLATE_MAP` whenever the manifest has no matching
slide — passing no manifest (the default) leaves every existing caller's
behavior unchanged. See [`docs/feature.md`](feature.md) for the CLI usage
and consumption details.

---

## 6. Validation

`src/core/validation/validator.py` runs two independent passes, neither
required for the other:
- `ProgrammaticValidator` — deterministic checks (markdown artifacts,
  known template placeholders left unreplaced, file-size heuristics),
  config-driven via `default_rules.yaml`.
- `LLMValidator` (optional, requires `--llm`) — sends extracted text to a
  configured LLM and asks for a JSON list of issues (`TRUNCATED`,
  `GARBLED`, `PLACEHOLDER_LEAK`, `MISMATCH`, `EMPTY_SECTION`). Any failure
  (no provider, malformed response, extraction error) returns an empty
  result rather than blocking the pipeline.

Neither pass replaces an actual visual check — this library's own source
rule file treats "render to PDF and look at it"
(`libreoffice --headless --convert-to pdf` + `pdftoppm`) as non-negotiable
before calling any generated file done.

---

## 7. Compatibility

All additions described here (extraction pipeline, layout manifests) are
backward compatible and additive — the original `convert`/`batch`/`watch`
commands and the static `DEFAULT_TEMPLATE_MAP` path continue to work
unchanged when a manifest isn't supplied.
