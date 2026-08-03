# XLSX: Sheet Generation + LLM-Driven Reorganization

Unlike PPTX/DOCX, XLSX has no "template design" to risk corrupting in the same sense —
build sheets directly with **`openpyxl`'s high-level API**. Every cell, style and
dimension is set explicitly, so there's no inherited template state to silently lose.

## Working Method

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

wb = Workbook()
ws = wb.active
ws.title = sheet_def.name

THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="2E75B6")
HEADER_FONT = Font(bold=True, color="FFFFFF")

for col_idx, col_name in enumerate(sheet_def.columns, start=1):
    cell = ws.cell(row=1, column=col_idx, value=col_name)
    cell.font, cell.fill, cell.border = HEADER_FONT, HEADER_FILL, BORDER
    cell.alignment = Alignment(horizontal="center")

for row_idx, row in enumerate(sheet_def.rows, start=2):
    for col_idx, value in enumerate(row, start=1):
        cell = ws.cell(row=row_idx, column=col_idx, value=value)
        cell.border = BORDER

for col_idx, col_name in enumerate(sheet_def.columns, start=1):
    letter = ws.cell(row=1, column=col_idx).column_letter
    width = max(len(str(col_name)), *(len(str(r[col_idx-1])) for r in sheet_def.rows if col_idx-1 < len(r)))
    ws.column_dimensions[letter].width = min(width + 2, 60)

ws.freeze_panes = "A2"
```

## LLM-Driven Sheet Reorganization (Avoiding Fragmentation)

A naive "one sheet per markdown section" produces fragmented, hard-to-read workbooks.
Where an LLM is available, have it **reorganize parsed sections into logical sheet
archetypes before generation** — exactly the proven pattern in `SpreadsheetReorganizer`:

- Convert sections to a JSON summary; ask the LLM to classify/group into one of:
  `dashboard`, `breakdown`, `timeline`, `comparison`, `matrix`, `raw` — capped at
  `max_sheets` (default 10).
- **Always keep a rule-based fallback** for when no LLM is configured:
  - **KPI extraction**: regex for `"Metric: $Value"` patterns → synthesize a Dashboard sheet
  - **Table fingerprinting**: group raw tables by `(column_count, header_names)`
  - **Consolidation**: merge fingerprint-matched tables into one sheet with a `Category`
    prefix column instead of N near-duplicate sheets
- **Separation of concerns**: the LLM only ever decides *grouping/labels*; the actual
  cell-writing always goes through the safe `openpyxl` path above. Same principle as the
  layout manifest — LLM picks, proven code executes (see
  [layout-manifest.md](layout-manifest.md)).

## Verification

```python
from openpyxl import load_workbook

def verify_xlsx(path, expected_sheet_count=None):
    wb = load_workbook(path)
    issues = []
    if expected_sheet_count and len(wb.sheetnames) != expected_sheet_count:
        issues.append(f"Expected {expected_sheet_count} sheets, found {len(wb.sheetnames)}")
    for ws in wb.worksheets:
        if ws.max_row < 2:
            issues.append(f"Sheet '{ws.title}' has no data rows")
        if ws.freeze_panes != "A2":
            issues.append(f"Sheet '{ws.title}' missing frozen header row")
    return issues
```

Also: `libreoffice --headless --convert-to pdf workbook.xlsx` for a visual spot-check, and
confirm no sheet exceeds `max_columns` (default 20) — and that the workbook isn't an
unreadable wall of near-duplicate raw-data sheets, which is exactly what the reorganizer
above exists to prevent.

## Images in XLSX

Not currently a proven recipe in this codebase — if a task requires embedding images in a
spreadsheet, treat it as new ground: build and visually verify the recipe first (same
discipline as `inject_template_image` for PPTX) before relying on it in an unattended
pipeline.
