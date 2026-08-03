# DOCX: Template Body Replacement (with Hardened Tables)

## Working Method

Load the branded template, clear its body content (while preserving logos/decorative
images), then copy paragraphs and tables from a pre-built "clean" source document — **in
original document order**, so tables stay inline rather than collapsing to the bottom.

### Step-by-Step

1. `template = Document('template.docx')`
2. Clear body — remove `<w:p>`/`<w:tbl>`, but **keep paragraphs containing images** (see
   below)
3. `source = Document('source-clean.docx')`
4. **Iterate `source.element.body` children in order**, copying each paragraph/table as
   you encounter it (not all paragraphs then all tables)
5. Copy paragraphs: new paragraph + copy every run with its font properties
6. Copy tables: matching dimensions, copy cell text, then **harden** (see below)
7. Sanitize markdown artifacts from every run
8. Save

### CRITICAL: Element Order Preservation

```python
# WRONG — tables end up dumped at the bottom:
for para in source.paragraphs: copy_paragraph(para, template)
for table in source.tables:    copy_table(table, template)

# CORRECT — tables stay inline with surrounding paragraphs:
para_idx = table_idx = 0
for child in source.element.body:
    tag = child.tag.split('}')[-1]
    if tag == 'p':
        copy_paragraph(source.paragraphs[para_idx], template); para_idx += 1
    elif tag == 'tbl':
        copy_table(source.tables[table_idx], template); table_idx += 1
```

### Body Clearing — WITH Image Preservation

Branded templates often carry a logo (e.g. company wordmark) in the first paragraphs.
**These must survive the clear.** Detect real drawing content, not just any paragraph:

```python
IMAGE_TAGS = {"drawing", "inline", "anchor", "blip"}

body = template.element.body
for child in list(body):
    tag = child.tag.split('}')[-1]
    if tag == 'p':
        has_image = any(d.tag.split('}')[-1] in IMAGE_TAGS for d in child.iter())
        if has_image:
            continue            # KEEP — logo / decorative image
        body.remove(child)
    elif tag == 'tbl':
        body.remove(child)
```

This preserves logos, decorative lines, headers/footers, and section properties, while
clearing placeholder text paragraphs and tables (which get replaced by source content).

### Run & Paragraph Format Copy

```python
for src_run in src_para.runs:
    new_run = new_para.add_run(src_run.text)
    sf, nf = src_run.font, new_run.font
    if sf.bold is not None:   nf.bold = sf.bold
    if sf.italic is not None: nf.italic = sf.italic
    if sf.size is not None:   nf.size = sf.size
    if sf.name is not None:   nf.name = sf.name
    if sf.color and sf.color.rgb is not None: nf.color.rgb = sf.color.rgb

src_pf, new_pf = src_para.paragraph_format, new_para.paragraph_format
for attr in ('space_before', 'space_after', 'line_spacing', 'alignment',
             'left_indent', 'first_line_indent'):
    val = getattr(src_pf, attr)
    if val is not None:
        setattr(new_pf, attr, val)
```

---

## Table Injection — Build, Then Harden

Creating a table with `doc.add_table()` and a named style (e.g. `"Table Grid"`) is not
enough on its own — if the document later goes through Pandoc or any style-resolution
pass, unresolvable style references collapse the grid. **Harden every table** by writing
explicit, self-contained XML that doesn't depend on style resolution:

- Remove unresolvable `<w:tblStyle>` references
- Write explicit `<w:tblBorders>` (all edges, `style="single"`) directly on the table
- Set explicit per-column widths (`<w:tcW>`) on every cell — this is what actually keeps
  the grid from collapsing when the named style can't be resolved
- Strip unresolvable `<w:pStyle w:val="Compact">` from cell paragraphs

This is the difference between a table that "looks fine in python-docx" and one that
**survives round-tripping through LibreOffice/Pandoc** without losing its grid.

---

## Pandoc `--reference-doc` — Acceptable for DOCX, With Care

Unlike PPTX (where Pandoc rebuilds slides and is forbidden for precision work), Pandoc is a
viable DOCX path **if you post-process**. Known failure modes and mitigations:

| Issue | Cause | Mitigation |
|-------|-------|------------|
| Images not appearing | Relative paths broken, unsupported formats (WebP/SVG) | Resolve to absolute paths / copy to a working dir; convert unsupported formats with ImageMagick first |
| Footer/header lost or replaced with Pandoc defaults | Pandoc overwrites template `sectPr` references | Explicitly copy `headerReference`/`footerReference` from template `sectPr` to output `sectPr` post-conversion |
| Formatting drift | Markdown → DOCX mapping is lossy | Post-process with python-docx for anything precision-critical |
| Table formatting lost | Complex tables don't survive conversion | Reconstruct with python-docx + harden (above), don't rely on Pandoc's table output |

**Two-stage pipeline:** (1) Pandoc converts markdown → DOCX against the template as
`--reference-doc`; (2) a python-docx pass copies `headerReference`/`footerReference` XML
from the template's `sectPr` into the output's, re-harden any tables, and strip markdown
artifacts. Verify both image embedding (`rel.target_ref` contains `"image"`, blob
non-empty, every `<w:drawing>` has a `<a:blip>`) and header/footer presence
(`section.header.paragraphs[0].text` matches expectations) before declaring success.

---

## Verification Checklist

```bash
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.docx
pdftoppm -png -r 150 -f 1 -l 5 /tmp/verify/output.pdf /tmp/pages/page

# Confirm images embedded:
unzip -l output.docx | grep -c "media/"
# Confirm headers/footers survived:
unzip -p output.docx word/header1.xml | grep -o '<w:t[^>]*>[^<]*</w:t>' | head -5
unzip -p output.docx word/footer1.xml | grep -o '<w:t[^>]*>[^<]*</w:t>' | head -5
```

Then look at the rendered pages and check: branding/footer visible, title-page formatting
preserved, heading colors correct, bullets indented, **tables have visible borders and
correct column widths** (the hardening payoff), no markdown artifacts anywhere — check
table cells specifically, since `**bold**`/`*italic*` syntax surviving into a cell is the
most common leak point.
