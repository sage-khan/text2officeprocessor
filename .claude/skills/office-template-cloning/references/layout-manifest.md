# Template Layout Analysis — LLM-Consumable Manifests

How to analyze an **unfamiliar** template (one you don't already have a slide-index map or
placeholder map for) and produce a structured manifest that tells you — or an LLM acting on
your behalf — exactly which slide/section/sheet to use for a given piece of content,
whether it can host an image or table, and which *proven* recipe injects into it safely.

## Why This Exists

Hardcoding `SlideIntent → template_index` only works for one known deck. A new template
needs the same questions answered again: what kind of content does each slide suit, can it
host an image or table, how much text fits before overflow, and which proven recipe (from
[pptx-cloning.md](pptx-cloning.md) / [docx-injection.md](docx-injection.md) /
[xlsx-generation.md](xlsx-generation.md)) is safe for each of its slots. A manifest answers
these once per template instead of re-deriving them via ad-hoc regexes at generation time.

## The One Rule That Matters

**The manifest only ever *labels which existing proven recipe applies where*. It must
never invent new injection mechanisms.** This is what keeps "an LLM picks the
slide/slot" safely decoupled from "verified code performs the injection" — a wrong label
can only result in picking the wrong-but-still-safe recipe, never an unsafe one.

## What Goes in the Manifest

For every slide / DOCX section / XLSX sheet archetype, record:

- **`content_affinity`** — what kind of content it suits: `bullets`, `stats`,
  `key_highlights`, `comparison`, `timeline`, `image_heavy`, `table`, …
- **`capacity`** — rough text-length / item-count limits before overflow handling
  (summarize/split/shrink) needs to kick in
- **`slots[]`** — each editable region: its `kind` (native placeholder / textbox-pattern /
  grouped-diagram), what it `accepts` (`text` / `image` / `table`), its position & size,
  and which proven recipe applies (`single_run_replace`, `cross_run_replace`,
  `inject_template_image`, `set_section_text_boxes`, `docx_harden_table`,
  `slidepart_clone`, …)
- **`synthesis_guidance`** — when nothing fits: which existing slide is the closest
  structural match to clone-and-adapt, and which of its XML patterns to reuse (always via
  `slidepart_clone` — never freehand XML construction)

```jsonc
{
  "template_path": "templates/example.pptx",
  "format": "pptx",
  "slides": [
    {
      "index": 7,
      "layout_name": "Key Highlights 4-col",
      "content_affinity": ["key_highlights", "comparison", "feature_grid"],
      "capacity": { "title_max_chars": 60, "body_max_chars_per_slot": 140, "max_items": 4 },
      "slots": [
        { "role": "title", "kind": "placeholder", "accepts": ["text"], "injection_recipe": "single_run_replace" },
        { "role": "card_1", "kind": "text_run_pair", "accepts": ["text"], "injection_recipe": "cross_run_replace" },
        { "role": "image_slot_1", "kind": "picture_placeholder", "accepts": ["image"], "aspect_ratio": 1.333, "injection_recipe": "inject_template_image" }
      ],
      "tables": [],
      "clone_strategy": "slidepart_clone"
    }
  ],
  "synthesis_guidance": {
    "closest_match_by_intent": { "stats_grid": 7, "timeline": 11 },
    "forbidden": ["add_slide(layout) alone", "deepcopy(slide)", "shape.left reassignment"]
  }
}
```

DOCX manifests use `sections` (style runs, table-capable regions, image-anchor paragraphs)
instead of `slides`; XLSX manifests use `sheet_archetypes`, reusing the
`dashboard`/`breakdown`/`timeline`/`comparison`/`matrix`/`raw` vocabulary from
[xlsx-generation.md](xlsx-generation.md).

## How to Generate One

1. **Structural pass (deterministic)** — enumerate slides/sections/sheets, shapes,
   placeholders, run structure, and positions. This is ground truth: it always overrules
   LLM guesses for anything measurable (counts, positions, run structure).
2. **Classification pass (LLM)** — feed the structural data (never the binary file) to an
   LLM and ask it to assign `content_affinity`, `capacity`, `slots[].accepts`, and pick
   `injection_recipe` from the fixed enum, using shape *kind* as the deciding signal:
   - native placeholder → `single_run_replace` / `inject_template_image`
   - textbox matching a content pattern (e.g. "SECTION NAME") → `set_section_text_boxes`
   - grouped/freeform diagram (group_count > 3 or freeform_count > 5) → pattern-matching
     by content + position-sort, never by placeholder type
3. **Merge & persist** — structural facts win on conflict; save as
   `<template_stem>.layout-manifest.json`; regenerate only when the template changes
   (mtime/hash check).
4. **Verify before trusting** — run the manifest's slot/recipe labels through the same
   visual-verification pipeline (rendered PDF/PNG inspection) used for real generations. A
   manifest that mislabels a slot as `accepts: ["image"]` is exactly the class of error
   visual inspection catches and a schema check cannot.

## How Generation Consumes It

For each content block and its intent/content-type:

1. Filter slides/sections to those whose `content_affinity` matches.
2. Pick the best capacity fit — avoids triggering overflow handling unnecessarily.
3. Image present but no slot `accepts: ["image"]`? → choose a different slide, or fall
   back to text-only. **Never** force an image onto a layout that can't host one, and
   never `add_textbox()`/`add_picture()` at an arbitrary position to "make room."
4. Tabular content? → route to a slide/section/sheet whose slots accept tables. PPTX
   templates rarely do (prefer a grid/comparison layout, or flatten to bullets — see
   [pptx-cloning.md](pptx-cloning.md)); DOCX and XLSX both support real tables.
5. Nothing fits? → use `synthesis_guidance` to clone the closest structural match
   (`slidepart_clone`) and adapt it. Record the new type back into the manifest so future
   runs reuse it instead of re-synthesizing from scratch.

## Non-Goals / Guardrails

- The manifest is **advisory metadata**, not executable code.
- It never overrides the geometry/background/relationship-preservation rules — it only
  *reads* the template to decide *where content goes*, never *how the template looks*.
- Treat a freshly generated manifest as a draft until it has passed visual verification at
  least once on real generated output.
