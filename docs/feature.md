# Features

New capabilities, one dated section per feature (newest first). For "how
the system is built," see [`docs/architecture.md`](architecture.md); for
"what changed and when" at the line/commit level, see
[`docs/changelog.md`](changelog.md).

---

## 2026-08-20 — Layout manifests (`analyze-template --manifest`)

Static template mapping (`ContentPlanner.DEFAULT_TEMPLATE_MAP`) only knows
the one bundled 13-slide PPTX bank. Any other template required
hand-writing a `--slides-md` file with exact `template_index` values,
because nothing inspected an unfamiliar template and reported which slide
fits "four stats," whether a slot takes an image, or whether a table will
fit.

A **layout manifest** is a JSON file describing what a template can hold
and how to safely fill it — generated once per template, cached, and
consumed by `ContentPlanner` to pick slides for a template it's never seen
before.

### Generating a manifest

```bash
# Structural pass only (deterministic, no LLM required)
text2officeprocessor analyze-template my-template.pptx --manifest my-template.pptx.layout-manifest.json

# With an LLM classification pass (refines content_affinity + notes)
text2officeprocessor analyze-template my-template.pptx \
  --manifest my-template.pptx.layout-manifest.json \
  --llm ollama --llm-model mistral
```

Works for `.pptx` and `.docx` templates. `.xlsx` is not supported —
`XLSXEngine` builds sheets directly with no template to clone, so there's
no injection-safety contract for a manifest to describe (see
[`docs/architecture.md`](architecture.md) §3.3/§5).

The manifest is cached next to the template as
`<template_stem>.layout-manifest.json` and only regenerated when the
template file changes (or `--manifest` is re-run, which always forces
regeneration). Loading it programmatically:

```python
from src.core.analysis.manifest import get_or_generate_manifest

manifest = get_or_generate_manifest(Path("my-template.pptx"))
```

### What's in it

- **PPTX** — one `SlideManifest` per slide: its `content_affinity`
  (`bullets`, `key_highlights`, `diagram`, ...), estimated text `capacity`,
  each slot's `accepts` (`text`/`image`/`table`) and `injection_recipe`
  (one of a fixed, safe enum — `single_run_replace`, `set_bullets`,
  `apply_items`, `inject_template_image`, ...).
- **DOCX** — one `SectionManifest` per heading style actually used in the
  template, plus a `body` section reporting whether the template has any
  tables (`supports_table`) or inline images (`has_image_anchor`).

The manifest is **advisory metadata, never executable logic** — an LLM
classification pass can only pick among the fixed recipe names above; it
can never invent a new injection mechanism, so a bad guess is bounded to
"labelled the wrong but still-safe recipe," never an unsafe operation.
Structural facts (positions, shape counts) always come from direct
template inspection and always win over an LLM guess.

### Using a manifest during generation

Pass a loaded `TemplateManifest` to `ContentPlanner`; it's consulted per
slide via `content_affinity` before falling back to the bundled template's
static mapping:

```python
from src.core.planner.content_planner import ContentPlanner
from src.core.analysis.manifest import get_or_generate_manifest

manifest = get_or_generate_manifest(Path("my-template.pptx"))
planner = ContentPlanner(manifest=manifest)
```

Not passing a `manifest` (the default) leaves behavior exactly as it was
before this feature — only the bundled generic template bank is used, via
`DEFAULT_TEMPLATE_MAP`, same as every prior release.

### Non-goals

- No CLI flag yet to pass a manifest straight into `convert`/`batch` —
  today it's a library-level `ContentPlanner(manifest=...)` API. Wiring it
  into the CLI end-to-end is a natural follow-up once there's a real
  non-bundled template to validate it against.
- The manifest never edits or moves anything in the template — it's a read
  pass. Verify with a real render before trusting a manifest for
  unattended use on a template you haven't visually checked yet.
