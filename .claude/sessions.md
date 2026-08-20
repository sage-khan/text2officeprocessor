# Session Log

Newest entry first. See `.claude/tasks.md` for the live working list this
log tracks against, and `.claude/memory.md` for durable decisions that
don't need re-litigating in a future session.

---

## 2026-08-20 — 0.5.2 shipped: layout manifests, apply_items fix, doc migration, and a real content-fitter bug found in verification

Dan approved the full `docs/internal/plan.md` scope inline, including the layout-manifest
system going into this same release (not deferred), and pointed at `veritas` (Tailscale
SSH server, see the auto-memory `reference-veritas-test-server` entry) for running the
heavy test/build work instead of the laptop.

**Shipped**:
- Doc migration (§1): flat `docs/changelog.md`/`docs/diagnostics.md` (already staged from
  a prior pass), `docs/development/implementation-v2.md` → rewritten as
  `docs/architecture.md`, new `docs/feature.md`, `docs/development/` removed.
- `apply_items()` fix (§2.1): unfilled grid/card slots now have their shape removed
  instead of leaking template placeholder text or this library's own literal item-key
  names. Two new regression tests.
- DOCX table-hardening spot-check (§2, last bullet): rendered `sample-summary.md`'s table
  through the Pandoc path against `generic-document.docx`, verified via direct XML
  inspection and a `libreoffice --headless` + `pdftoppm` visual render. No defect —
  matches the documented recipe exactly.
- Layout manifest system (§3, full spec): new `src/core/analysis/manifest.py`
  (structural pass reused from `structural.py`, optional LLM classification pass with
  `INJECTION_RECIPES`-validated merge, mtime-based caching), a new DOCX structural pass
  (`build_docx_section_manifests`), `analyze-template --manifest` CLI wiring, and
  `ContentPlanner(manifest=...)` consumption (falls back to the static
  `DEFAULT_TEMPLATE_MAP` when unset — every existing caller's behavior is unchanged).
  XLSX intentionally out of scope (no template-cloning risk to describe). 18 new tests.
- **Real bug found during golden-path verification** (not in the original plan): with an
  LLM provider configured (the CLI's default whenever one is reachable),
  `PPTXContentFitter.fit_slide_plan()` was unconditionally injecting a literal `"title"`
  key into every slide's `replacements` dict, which `replace_text_everywhere()`'s
  substring matching then used to silently delete the text "title" wherever it appeared
  on a slide — corrupting `card_1_title`/`card_2_title` into `card_1_`/`card_2_` even
  when those slots were correctly matched and filled. Live since 0.4.1, on every default
  `convert` invocation with a reachable LLM. Fixed in `content_fitter.py`; three new
  regression tests (two at the fitter level, one full-pipeline render). Confirmed fixed
  via a real `libreoffice`-rendered PNG.
- Version bump 0.5.1 → 0.5.2 (`pyproject.toml`, `src/web/app.py`'s nav badge + FastAPI
  `version=`), `docs/changelog.md` entry, `.claude/tasks.md` cleared.

**How it was executed**: all code changes made locally; `pytest`/`ruff`/`mypy` run
remotely on `veritas` after each meaningful change (rsync + venv already set up there),
per Dan's instruction not to overload the laptop. LibreOffice visual-verification renders
done locally (lightweight, and veritas doesn't have LibreOffice installed / no
passwordless sudo there to install it). Final state: 255/255 tests passing.

**Still open**: nothing from this pass. `docs/internal/plan.md` stays gitignored/local —
its content is now fully reflected in `docs/changelog.md` and `docs/architecture.md`/
`docs/feature.md`. Not yet committed — awaiting Dan's go-ahead on the commit itself.

---

## 2026-08-20 — Next-version release plan drafted (awaiting approval)

Dan asked for a full pass over this codebase plus
`~/ProgramFiles/ec-council`'s md-to-pptx/docx rules and skills
(`md2ppt-docx.mdc`, `office-template-cloning`, `office-template-fill`), and
to bring this repo's session-continuity system up to `creator-flow`'s
current conventions before planning the next release.

**Findings**: most of the rule file's historically-documented defect
classes are already fixed here with regression tests (SlidePart clone
rId preservation, 3-layer text replace, `set_bullets()` slot removal +
indent normalization, font-shrink cap, image-slot detect + crop-to-fit).
One confirmed, untested gap: `apply_items()`/`_replace_card()` leaves
unfilled grid/card slots (Key Highlights/Features/Benefits/Excellence
Grid) with the template's literal placeholder text still visible instead
of removing the shape — zero test coverage on that path. Also confirmed
`.claude/memory.md`'s documentation-convention decision (flat
`docs/changelog.md`/`docs/diagnostics.md`, no `docs/development/`
subfolder) was written down but never actually executed — the repo still
has `docs/development/*`.

**Done this session**:
- Created `docs/internal/` (gitignored, added to `.gitignore`) matching
  `creator-flow`'s convention exactly, for release-planning drafts.
- Wrote the full plan to `docs/internal/plan.md`: doc migration, the
  `apply_items()` fix, a DOCX table-hardening spot-check, and an explicit
  scoping question for the (currently stub) Layout Manifest system in
  `src/core/analysis/` — recommended deferring that to its own release
  rather than folding it into this patch.
- Logged the plan as a checklist in `.claude/tasks.md`.

**Still open**: waiting on Dan to approve/revise `docs/internal/plan.md`
before any of it is executed.

---

## 2026-08-19 — Session continuity system (sessions.md, memory.md, tasks.md)

Set up the same session-continuity pattern used in
`coder-with-vibes-taylor-francis` and `ec-council`, applied here for
consistency across Dan's repos: this file (`.claude/sessions.md`, dated
append-only log, read first when resuming, written before ending any
session or risky operation), `.claude/memory.md` (durable decisions, not a
diary), and `.claude/tasks.md` (live working list, annotated with `DAN:`
lines for Dan's own decisions, folded into `docs/changelog.md` once
emptied per `.devin/rules/code-review-guidelines.md`'s documentation
convention). All three live under `.claude/`, not the repo root — this is a
public PyPI package (`text2officeprocessor`), so keeping the root minimal
matters.

**Still open:** none from this pass. `memory.md` and `tasks.md` are freshly
seeded and will need real entries as work actually happens.
