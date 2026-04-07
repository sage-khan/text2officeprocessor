# Diagnostics

Bug fixes and issue resolutions. Append-only with timestamps.

---

## [2026-04-07] DOCX engine — KeyError on heading styles with custom templates

**Symptom:** `KeyError: "no style with name 'Heading 2'"` when injecting sections into EC-Council branded DOCX templates that use custom style names rather than standard Word styles.

**Root cause:** `python-docx` `add_heading(level=N)` internally calls the style `"Heading N"` which must exist in the document's style registry. EC-Council templates use branded style names.

**Fix:** Wrapped `add_heading()` in a try/except; falls back to a plain bold paragraph run when the heading style is not present. Same pattern applied to `List Bullet` style in `_add_list_item()`.

**Files changed:** `src/core/engines/docx/engine.py`

---

## [2026-04-07] Planner test — spreadsheet assertion on wrong sheet index

**Symptom:** `test_spreadsheet_plan_from_markdown` failed with `AssertionError` because `plan.sheets[0]` was an empty section (the H1 document title creates an empty section before the first H2).

**Root cause:** The preprocessor creates a section for every heading including the H1. The first section has no content blocks — content belongs to the `## Sales Data` section.

**Fix:** Updated test assertion to search across all sheets for the first one with data (`columns or rows`), rather than assuming index 0.

**Files changed:** `tests/test_planner.py`
