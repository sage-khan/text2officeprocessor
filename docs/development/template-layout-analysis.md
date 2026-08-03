# Template Layout Analysis — LLM-Consumable Manifests

> Status: design spec for the (currently stub) `src/core/analysis/` package.
> Companion to the structural extraction in `src/core/extraction/` (`ExtractedStyleSheet`,
> `PlaceholderInfo`, `PptxSlideLayout`) — extraction captures *what a template looks like*,
> this layer adds *what each part of it is for and how to safely fill it*.

## 1. Problem

Today, slide-to-template mapping is static: `content_planner.DEFAULT_TEMPLATE_MAP` hardcodes
`SlideIntent → template_index` for the one bundled 13-slide deck, and any other template
requires the user to hand-write a `--slides-md` file that names exact `template_index`
values. Nothing inspects a *new* template and tells the planner (or an LLM) which slide to
clone for "four stats", whether a slot can take an image vs. text-only, whether a table will
fit, or how to inject into it without corrupting the file.

`image_injector.py` and `_harden_tables()` already encode *safe injection recipes* per slot
type — but they discover slots at generation time, per-run, with regexes. That knowledge
should be captured once, per template, as a manifest that both the planner and an LLM can
read.

## 2. Goal

A CLI step — `analyze-template <file> --manifest out.json` — that produces a single JSON
**layout manifest** per template (PPTX, DOCX, or XLSX). The manifest is the contract between
"what the template can do" and "what the content needs", consumed by:

- `ContentPlanner` to pick a `template_index`/section/sheet style for each content block,
  replacing/augmenting `DEFAULT_TEMPLATE_MAP`;
- an LLM prompt (see §5) that decides, per content block: *which slide type, does it need
  an image, does it need a table, will the text fit, or does a new slide type need to be
  synthesized*;
- the engines, as a lookup for *which injection recipe is safe* for a given slot.

## 3. Manifest schema (draft)

Builds directly on `ExtractedStyleSheet` / `PptxSlideLayout` / `PlaceholderInfo`
(`src/core/extraction/models.py`) — this is an additive layer, not a replacement.

```jsonc
{
  "template_path": "templates/ec-council-section.pptx",
  "format": "pptx",
  "generated_at": "2026-06-08T00:00:00Z",
  "dimensions": { "slide_width_emu": 12192000, "slide_height_emu": 6858000 },

  "slides": [
    {
      "index": 7,
      "layout_name": "Key Highlights 4-col",

      "content_affinity": ["key_highlights", "comparison", "feature_grid"],
      "capacity": {
        "title_max_chars": 60,
        "body_max_chars_per_slot": 140,
        "max_items": 4
      },

      "slots": [
        {
          "role": "title",
          "kind": "placeholder",
          "placeholder_type": "TITLE",
          "match_text": "Key Highlights",
          "position_emu": { "left": 838200, "top": 365760, "width": 9144000, "height": 914400 },
          "accepts": ["text"],
          "injection_recipe": "single_run_replace"
        },
        {
          "role": "card_1",
          "kind": "text_run_pair",
          "match_text": "Key Element Title 01",
          "accepts": ["text"],
          "injection_recipe": "cross_run_replace"
        },
        {
          "role": "image_slot_1",
          "kind": "picture_placeholder | textbox_pattern",
          "match_pattern": "\\[Image placeholder\\]|Photo here",
          "position_emu": { "left": 1219200, "top": 1828800, "width": 2743200, "height": 2057400 },
          "accepts": ["image"],
          "aspect_ratio": 1.333,
          "injection_recipe": "inject_template_image"
        }
      ],

      "tables": [
        {
          "role": "data_table_1",
          "max_rows": 6,
          "max_cols": 4,
          "injection_recipe": "docx_harden_table | none_supported"
        }
      ],

      "clone_strategy": "slidepart_clone",
      "notes": "4 alternating cards; titles + bodies are 2-run paragraphs; do not use add_slide()."
    }
  ],

  "synthesis_guidance": {
    "closest_match_by_intent": { "stats_grid": 7, "timeline": 11 },
    "xml_patterns_to_reuse": ["Key Highlights 4-col uses 4 grouped Rectangles with title+body runs — clone and retitle for N-up grids"],
    "forbidden": ["add_slide(layout) alone", "deepcopy(slide)", "shape.left reassignment"]
  }
}
```

Notes:
- `kind` / `injection_recipe` values are an enum tied 1:1 to **proven methods already in the
  rule file** (`slidepart_clone`, `single_run_replace`, `cross_run_replace`,
  `inject_template_image`, `docx_harden_table`, `set_section_text_boxes`, …). The manifest
  never invents a new mechanism — it only *labels which existing one applies where*.
- `content_affinity` and `capacity` are the fields an LLM uses to choose a slide for a given
  content block; `slots[].accepts` is what tells it whether an image/table is even possible
  there, so it doesn't try to force one into a text-only layout.
- DOCX manifests use `sections` (style runs, table-capable regions, image-anchor paragraphs)
  instead of `slides`; XLSX manifests use `sheet_archetypes` (dashboard/breakdown/timeline/…
  — reusing the vocabulary already defined in `default_rules.yaml`'s spreadsheet reorganizer).

## 4. How it's generated

1. **Structural pass (deterministic, existing code)** — reuse `extract_styles()` +
   `analyze` CLI's shape inspection (`src/cli/main.py` `analyze_template_cmd`) to enumerate
   slides/sections/sheets, shapes, placeholders, run structure, and any
   "guessed_slide_type" heuristics already computed.
2. **Classification pass (LLM)** — feed the structural JSON (never the binary file) to the
   LLM with a prompt that asks it to: name each slide's `content_affinity`, estimate
   `capacity`, mark which slots `accepts: ["image"|"table"|"text"]`, and pick the
   `injection_recipe` from the fixed enum based on the *shape kind* it sees (placeholder vs.
   textbox-pattern vs. grouped-diagram — mirroring the COV-template heuristics already in
   §6 of the rule file).
3. **Merge & validate** — structural data wins over LLM guesses for anything measurable
   (positions, counts, run structure); the LLM only contributes the *semantic* labels
   (affinity, recipe choice, synthesis guidance) that can't be derived mechanically.
4. Persist as `<template_stem>.layout-manifest.json` next to the template, cached and
   reused across runs (regenerate only if the template's mtime/hash changes).

## 5. How the planner/LLM uses it at runtime

For each `(SlideIntent, SlideContent)` pair, instead of (or in addition to) the static
`DEFAULT_TEMPLATE_MAP` lookup:

1. Filter `manifest.slides` by `content_affinity` matching the intent.
2. Among matches, pick the one whose `capacity` best fits the actual content size (avoids
   triggering `PPTXContentFitter` overflow handling unnecessarily).
3. If `SlideContent` carries an image (`visual_hint == IMAGE` / `diagram_path`/`image_path`
   set) but the chosen slide has no slot with `accepts: ["image"]`, either pick a different
   slide that does, or fall back to text-only — never force an image onto a layout that
   can't host one.
4. If content is tabular (`ContentType.TABLE` / `VisualHint.TABLE`) and the target format
   supports table slots in this slide (DOCX: yes via `_harden_tables`; PPTX: generally no —
   prefer a "Key Highlights" / grid-style slide instead, or convert the table to bullets),
   route accordingly.
5. **No matching slide exists** → consult `synthesis_guidance`: clone the
   `closest_match_by_intent` slide and apply the labelled `xml_patterns_to_reuse` to derive
   a new slide type that is structurally consistent with the template (still via
   `slidepart_clone` — never freehand XML construction). Record the synthesized type back
   into the manifest so subsequent runs reuse it.

## 6. Non-goals / guardrails

- The manifest is **advisory metadata**, not executable code — it never contains injection
  *logic*, only *labels* selecting among the fixed, proven recipes documented in the rule
  file (`md2ppt-docx` / `md2office-rules`). This keeps "LLM picks the slide" decoupled from
  "verified code performs the injection", so a bad LLM guess can only result in picking the
  wrong (but still safe) recipe — never an unsafe one.
- Mirrors the existing **NON-NEGOTIABLE RULES**: layout geometry, backgrounds, fonts and
  relationships must never be touched by the analysis step; it only reads.
- Manifest generation must run the same **visual verification pipeline**
  (`libreoffice --headless --convert-to pdf` + `pdftoppm`) the rule file already mandates,
  before a manifest is trusted for unattended use — a manifest that mis-labels a slot as
  `accepts: ["image"]` is exactly the kind of error that visual inspection catches and a
  schema check cannot.
