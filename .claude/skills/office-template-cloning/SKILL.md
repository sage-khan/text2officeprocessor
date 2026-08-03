---
name: office-template-cloning
description: "Use this skill whenever the task is to take an EXISTING branded PPTX, DOCX, or XLSX template (with a fixed background, theme, fonts, logos, picture slots, complex diagrams, or section/sheet structure) and inject new content into it from markdown or structured data WITHOUT breaking its design — i.e. the result must look like it was made from the same template, not rebuilt from scratch. Trigger on phrases like \"use this template,\" \"keep the branding/theme/layout,\" \"don't break the slides/formatting,\" \"clone this slide,\" \"fill in the placeholders,\" \"inject images into the template,\" \"preserve the header/footer/logo,\" or any md-to-pptx/md-to-docx/md-to-xlsx generation against a corporate deck or document template. Also use it when deciding HOW to analyze an unfamiliar template before generating against it (which slide/section/sheet to use for which content, whether a slot can hold an image or table, and how to inject into it safely) — i.e. building or consuming a template layout manifest. Prefer this skill over generic unpack/edit/pack approaches when the template has complex backgrounds, grouped diagrams, or picture placeholders, since naive rebuilding (add_slide, deepcopy, Pandoc --reference-doc) is the single most common cause of broken-looking output."
license: Proprietary — internal use
---

# Office Template Cloning (PPTX / DOCX / XLSX)

Battle-tested methods — extracted from `text2officeprocessor` and the `md2ppt-docx` /
`md2office-rules` rule files — for converting markdown/structured content into
template-compliant Office documents **without** corrupting or visually degrading the
template. Every method here has been verified by visual (rendered-PDF) inspection; the
generic "unpack XML → edit → repack" approach in the bundled `pptx`/`docx`/`xlsx` skills is
a fine default for simpler edits, but **for templates with backgrounds, picture
placeholders, grouped diagrams, or strict branding, use the recipes below instead.**

## Core Principle

> Preserve template structure exactly. Clone at the part/XML level. Inject content at the
> run level only. Never rebuild from scratch.

| Don't | Why it breaks things | Do instead |
|-------|----------------------|------------|
| `add_slide(layout)` | Loses backgrounds, breaks picture placeholders | `duplicate_slide()` — SlidePart clone, see [pptx-cloning.md](references/pptx-cloning.md) |
| `copy.deepcopy(slide)` | Corrupts package relationships | SlidePart clone with explicit `rels` copy |
| Pandoc `--reference-doc` for PPTX | Rebuilds slides, loses complex layouts | SlidePart clone (PPTX); Pandoc is acceptable for DOCX *with* post-processing, see [docx-injection.md](references/docx-injection.md) |
| `text_frame.clear()` / `text_frame.text = "..."` | Destroys run-level formatting | Run-level replacement (3-layer strategy, see below) |
| `shape.left = ...` / moving shapes | Breaks diagram/grid layouts | Never reposition; only edit text/picture fill in place |
| `slide.shapes.add_table()` on a cloned slide | New shape outside template's design system, fragile | Map onto an existing grid/comparison layout, or flatten to bullets |
| Guessed-coordinate `add_picture()` | Overlays template content; stretched/letterboxed images | Slot-detection + crop-to-aspect, see [pptx-cloning.md](references/pptx-cloning.md) |

## Quick Reference

| Task | Reference |
|------|-----------|
| Clone a template slide and inject text/images into it | [pptx-cloning.md](references/pptx-cloning.md) |
| Replace body content of a DOCX template while preserving headers/footers/logos, and inject hardened tables | [docx-injection.md](references/docx-injection.md) |
| Generate XLSX sheets/tables from scratch and reorganize fragmented data into logical sheets | [xlsx-generation.md](references/xlsx-generation.md) |
| Analyze an unfamiliar template and decide which slide/section/sheet + recipe fits a piece of content | [layout-manifest.md](references/layout-manifest.md) |

## The 3-Layer Text Replacement Strategy (PPTX & DOCX)

Template text is often split across runs/paragraphs and uses curly quotes. Always apply, in
order:

1. **Normalize curly quotes** (`‘’“”` → straight) before any comparison.
2. **Single-run match** — most common case; if the replacement consumes the whole run,
   blank out subsequent runs in the same paragraph (titles split like `"EXCELLENCE IN THE"`
   + `"MAKING"` will otherwise leave a dangling remnant).
3. **Cross-run match** — when old text spans multiple runs in one paragraph, join all run
   text, replace in the joined string, write the result into `runs[0]`, and blank the rest.

Full code for all three layers is in [pptx-cloning.md](references/pptx-cloning.md) §Text
Replacement (the same pattern applies verbatim to `python-docx` paragraphs).

## Verification Is Not Optional

Every generated file must pass visual inspection before being considered done — schema/type
checks cannot catch "looks broken":

```bash
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.{pptx,docx,xlsx}
pdftoppm -png -r 150 /tmp/verify/output.pdf /tmp/verify/page
# Then actually look at the PNGs (or use the Read tool on them)
```

PPTX file-size heuristic for the rendered slide PNGs: **<50KB ⇒ missing background** (broken
clone), 50–150KB ⇒ acceptable text-only slide, 200–500KB ⇒ full background preserved.

## Non-Negotiable Rules

1. If a method risks layout drift, style loss, markdown leakage, or file corruption — it
   must not be used, no matter how convenient.
2. Only surgical, in-place modification and verified pipelines are allowed.
3. Every generated file must pass visual verification (rendered PDF/PNG inspection).
4. No markdown artifacts (`**`, `__`, `---`, `***`) may remain in any final document —
   strip them from every run, especially inside table cells.
5. Template backgrounds, fonts, colors, layout positions, and relationships must be
   preserved exactly — read [layout-manifest.md](references/layout-manifest.md) for how to
   *decide* what content goes where without ever needing to touch geometry.
