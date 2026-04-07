---
trigger: manual
description: Document Generation Rules - PPTX/DOCX Production (Proven Methods)
---

# DOCUMENT GENERATION PROTOCOL

Proven, working methods for converting markdown content into template-compliant PPTX and DOCX files. Every method below has been tested and verified with visual inspection.

---

# PART 1: MD to PPTX (SlidePart Clone + Inject)

## 1.1 Core Principle

Preserve template structure exactly. Clone slides at the XML part level. Inject content at the run level only. Never rebuild slides, never modify layout geometry, never use `add_slide()` alone.

## 1.2 The Working Method: SlidePart Cloning

### Why Other Methods Fail

| Method | Problem |
|--------|---------|
| `add_slide(layout)` + shape copy | Loses background images, breaks Picture Placeholders |
| `copy.deepcopy(slide)` | Breaks internal relationships, corrupts package |
| Pandoc `--reference-doc` | Rebuilds slides from scratch, loses complex layouts |
| `add_slide(layout)` alone | Only gets layout structure, no slide-specific content |

### Working Clone Function (python-pptx 1.0.2+)

```python
import copy
from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import PackURI
from pptx.parts.slide import SlidePart

def duplicate_slide(prs, slide_index):
    """Clone a template slide preserving backgrounds, images, and all formatting."""
    source_slide = prs.slides[slide_index]
    source_part = source_slide.part

    # Deep copy the slide XML element
    new_xml = copy.deepcopy(source_part._element)

    # Determine next available slide number
    nums = []
    for s in prs.slides:
        m = re.search(r'slide(\d+)', str(s.part.partname))
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums) + 1 if nums else 1

    new_partname = PackURI(f'/ppt/slides/slide{next_num}.xml')

    # Create SlidePart with: (partname, content_type, package, element)
    new_part = SlidePart(
        new_partname,
        source_part.content_type,
        prs.part.package,
        new_xml
    )

    # Copy ALL relationships (images, layouts, hdphoto, etc.)
    for rel_key in source_part.rels:
        rel = source_part.rels[rel_key]
        new_part.rels.get_or_add(rel.reltype, rel._target)

    # Register in presentation
    rId = prs.part.relate_to(new_part, RT.SLIDE)

    # Add to sldIdLst
    sldIdLst = prs.slides._sldIdLst
    existing_ids = [int(e.get('id')) for e in sldIdLst if e.get('id')]
    new_id = max(existing_ids) + 1 if existing_ids else 256

    P_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    new_sldId = etree.SubElement(sldIdLst, f'{{{P_NS}}}sldId')
    new_sldId.set('id', str(new_id))
    new_sldId.set(f'{{{R_NS}}}id', rId)

    return prs.slides[len(prs.slides) - 1]
```

### Critical Notes on SlidePart Constructor

- **Signature:** `SlidePart(partname, content_type, package, element)`
- `package` = `prs.part.package` (NOT `source_part.package`)
- `element` = deep-copied lxml Element (NOT bytes, NOT blob)
- Do NOT use keyword arguments. Positional only.
- The `XmlPart.__init__` signature differs from `Part.__init__`. XmlPart expects `element`, Part expects `blob`.

---

## 1.3 Text Replacement Strategy

### Three-Layer Replacement

Text in PPTX templates can be split across runs, paragraphs, or contain curly quotes. The replacement function MUST handle all three cases.

#### Layer 1: Normalize Curly Quotes

```python
def _normalize(text):
    return text.replace('\u2018', "'").replace('\u2019', "'") \
               .replace('\u201c', '"').replace('\u201d', '"')
```

Template text often uses curly quotes (`\u2019` for apostrophe). Markdown uses straight quotes. Always normalize both sides before comparison.

#### Layer 2: Single-Run Match (Most Common)

```python
for run in paragraph.runs:
    if old_norm in _normalize(run.text):
        run.text = _normalize(run.text).replace(old_norm, new_text)
        # If replacement consumed the full run, clear subsequent runs
        if _normalize(run.text.strip()) == new_text.strip():
            for r in paragraph.runs[ridx + 1:]:
                r.text = ""
        break
```

**Critical edge case:** When a title like "EXCELLENCE IN THE" + "MAKING" is stored as two runs in one paragraph, matching the first run and replacing it leaves "MAKING" dangling. After replacing the first run, check if the new text equals the full replacement, and if so, blank all subsequent runs.

#### Layer 3: Cross-Run Match (Same Paragraph)

When old text spans multiple runs (e.g., run[0]="That" + run[1]="'s how much"), join all run texts, match, then set merged text in run[0] and blank the rest:

```python
full_text = "".join(run.text for run in paragraph.runs)
if old_norm in _normalize(full_text):
    paragraph.runs[0].text = _normalize(full_text).replace(old_norm, new_text)
    for run in paragraph.runs[1:]:
        run.text = ""
```

### Common Template Text Patterns

| Template Text | Issue | Solution |
|---------------|-------|----------|
| `That\u2019s how much...` | Curly apostrophe | `_normalize()` before matching |
| `EXCELLENCE IN THE` + `MAKING` | Two runs, one paragraph | Clear subsequent runs after match |
| `Key Element Title 01` | Numbered variants | Match on `Key Element Title` prefix |
| `This is a sample text. You simply add...` | Body placeholder | Match on `sample text` or `simply add` |

---

## 1.4 Slides Markdown Format

Content is defined in a structured markdown file. Each slide specifies its template index and content.

### Format Specification

```markdown
## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Your Section Title"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Your Slide Title"
- bullets:
  - "First bullet point text"
  - "Second bullet point text"

---

## SLIDE 3 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "Your Title"
- placeholder: "Enter your subhead line here" → "Your Subtitle"
- card_1_title: "Card 1 Title"
- card_1_body: "Card 1 description text"
- card_2_title: "Card 2 Title"
- card_2_body: "Card 2 description text"
```

### Parsing Rules

- Slide headers: `## SLIDE N — template_index: N (Type Name)`
- Placeholders: `- placeholder: "old" → "new"` (single line)
- Bullets: `- bullets:` followed by indented `- "text"` lines
- Items: `- card_N_title:` / `- item_N_body:` / `- item_0N_title:` patterns
- Section separator `---` resets bullet mode

---

## 1.5 EC-Council Template Slide Index Map

For the AI Algorithmic Auditing course template (13 slides):

| Index | Type | Key Placeholders |
|-------|------|------------------|
| 0 | Section Header | "Section Name Here", "SECTION Number" |
| 1 | Video Title | "Video Name", "Section Name", "Video Number" |
| 2 | Single Point | "SINGLE POINT SLIDE" + body |
| 3 | Multi Point | "Multi Point Slide" + 6 bullet paragraphs (whitespace) |
| 4 | Callout | "A key point (or issue)!" |
| 5 | Stats | "+80%" + description (curly apostrophe) |
| 6 | Key Pointers 4-quad | 4 items with icons |
| 7 | Key Highlights 4-col | "Key Highlights" + "Key Element Title 01-04" |
| 8 | Key Pointers 5-card | 5 alternating cards |
| 9 | Features 6-pill | "Features" + 6x "Key Element Title Here" |
| 10 | Benefits 6-item | "Benefits" + 6x "Key Element Title Here" |
| 11 | Excellence Grid | "EXCELLENCE IN THE"+"MAKING" (2 runs) + 3 Rectangles |
| 12 | Next Video | "Name of the Next Video", "Next Video" |

### Template Analysis Command

Run this to analyze any template before building the slides markdown:

```python
from pptx import Presentation
prs = Presentation('template.pptx')
for i, slide in enumerate(prs.slides):
    print(f'\n=== SLIDE {i} (layout: {slide.slide_layout.name}) ===')
    for j, shape in enumerate(slide.shapes):
        if shape.has_text_frame:
            for k, para in enumerate(shape.text_frame.paragraphs):
                for r, run in enumerate(para.runs):
                    if run.text.strip():
                        print(f'  Shape {j} "{shape.name}" para[{k}] run[{r}]: {repr(run.text)}')
```

---

## 1.6 Removing Template Bank Slides

After cloning all content slides, remove the original template slides:

```python
def remove_original_slides(prs, count):
    sldIdLst = prs.slides._sldIdLst
    R_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    to_remove = list(sldIdLst)[:count]
    for sldId in to_remove:
        rId = sldId.get(f'{R_NS}id')
        sldIdLst.remove(sldId)
        if rId:
            try:
                prs.part.drop_rel(rId)
            except Exception:
                pass
```

---

## 1.7 PPTX Verification Pipeline

```bash
# 1. Convert to PDF
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.pptx

# 2. Extract slide images
mkdir -p /tmp/slide-images
pdftoppm -png -r 150 /tmp/verify/output.pdf /tmp/slide-images/slide

# 3. Check file sizes (background preservation indicator)
ls -la /tmp/slide-images/
```

### File Size Heuristics

| Size Range | Meaning |
|------------|---------|
| < 50 KB | Missing background, likely broken clone |
| 50-150 KB | Simple slide (no background image), acceptable |
| 200-500 KB | Full background preserved, correct |

### Visual Inspection Checklist

- Slide 1: Section title + number visible on dark background
- Video title slides: Video name, section name, video number all populated
- Multi-point slides: Bullets visible with checkbox icons
- Key Highlights: All 4 cards have custom titles and body text
- Excellence Grid: Title replaced (no "MAKING" remnant), 3 items filled
- Stats: Large number visible, description replaced
- Next Video: Correct next video name shown

---

# PART 2: MD to DOCX (Template Injection)

## 2.1 Working Method: Template Body Replacement

Load the EC-Council DOCX template, clear its body content, then copy all paragraphs and tables from a pre-built source DOCX (the CLEAN version).

### Step-by-Step

1. Load template: `template = Document('template.docx')`
2. Clear body: Remove all `<w:p>` and `<w:tbl>` elements from `template.element.body`
3. Load source: `source = Document('source-clean.docx')`
4. **Iterate body elements IN ORDER**: Loop through `source.element.body` children, copying paragraphs and tables in their original sequence
5. Copy paragraphs: For each source paragraph, create a new paragraph in template, copy all runs with font properties (bold, italic, size, name, color)
6. Copy tables: Create matching tables, copy cell text
7. Sanitize: Remove markdown artifacts from all runs
8. Save

### CRITICAL: Element Order Preservation

**WRONG approach** (tables end up at bottom):
```python
for para in source.paragraphs:
    copy_paragraph(para, template)
for table in source.tables:
    copy_table(table, template)  # All tables dumped at end!
```

**CORRECT approach** (tables stay in position):
```python
para_idx = 0
table_idx = 0
for child in source.element.body:
    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
    if tag == 'p':
        copy_paragraph(source.paragraphs[para_idx], template)
        para_idx += 1
    elif tag == 'tbl':
        copy_table(source.tables[table_idx], template)
        table_idx += 1
```

This preserves the exact document structure where tables appear inline with surrounding paragraphs.

### Body Clearing Code (with Image Preservation)

**CRITICAL:** EC-Council templates contain logo images (e.g., "EC-Council | Learning") in the first paragraphs. These MUST be preserved.

```python
body = template.element.body
preserved_count = 0

for child in list(body):
    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
    if tag == 'p':
        # Check if paragraph contains actual drawing/image elements
        has_image = False
        for descendant in child.iter():
            desc_tag = descendant.tag.split('}')[-1] if '}' in descendant.tag else descendant.tag
            if desc_tag in ('drawing', 'inline', 'anchor', 'blip'):
                has_image = True
                break
        
        if has_image:
            preserved_count += 1
            continue  # KEEP this paragraph - it has an image
        body.remove(child)
    elif tag == 'tbl':
        body.remove(child)

print(f"Preserved {preserved_count} paragraphs with images")
```

This preserves:
- EC-Council Learning logo (first paragraph)
- Decorative lines/images
- Headers, footers, and section properties

While clearing:
- Placeholder text paragraphs
- Tables (to be replaced with source content)

### Run Property Copy

```python
for src_run in src_para.runs:
    new_run = new_para.add_run(src_run.text)
    sf = src_run.font
    nf = new_run.font
    if sf.bold is not None: nf.bold = sf.bold
    if sf.italic is not None: nf.italic = sf.italic
    if sf.size is not None: nf.size = sf.size
    if sf.name is not None: nf.name = sf.name
    if sf.color and sf.color.rgb is not None: nf.color.rgb = sf.color.rgb
```

### Paragraph Format Copy

```python
src_pf = src_para.paragraph_format
new_pf = new_para.paragraph_format
for attr in ['space_before', 'space_after', 'line_spacing', 'alignment',
             'left_indent', 'first_line_indent']:
    val = getattr(src_pf, attr)
    if val is not None:
        setattr(new_pf, attr, val)
```

---

## 2.2 DOCX Verification

```bash
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.docx
pdftoppm -png -r 150 -f 1 -l 5 /tmp/verify/output.pdf /tmp/pages/page
```

### Checklist

- EC-Council footer/header visible
- Title page formatting preserved (centered, bold, branded colors)
- Chapter headings in teal/blue color
- Subheadings bold
- Bullet points properly indented
- Tables with borders
- No markdown artifacts (`**`, `*`, `---`, `__`,`**`) and check it especially within tables.
- Page breaks between chapters
- **Images properly embedded** (check media/ folder exists in DOCX)
- **Headers/footers preserved** (verify with `unzip -p doc.docx word/footer1.xml`)

---

## 2.3 Markdown to DOCX Conversion (Pandoc Alternative)

When using Pandoc to convert markdown to DOCX with `--reference-doc`:

### Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Images not appearing | Relative paths broken, missing image files | Use absolute paths or copy images to temp dir |
| Footer/header lost | Pandoc may overwrite template headers | Preserve headers/footers explicitly |
| Formatting drift | Markdown syntax doesn't map perfectly | Post-process with python-docx |
| Table formatting lost | Complex tables don't convert well | Use python-docx table reconstruction |

### Image Handling During Conversion

**Problem**: Pandoc markdown-to-DOCX often misses images when:
- Image paths are relative to markdown file location
- Images are referenced via URL (requires network)
- Image formats are unsupported (WebP, SVG without conversion)

**Pre-Conversion Checklist:**

```bash
# 1. Verify all images exist and are accessible
find . -name "*.md" -exec grep -l "!\[" {} \; | while read mdfile; do
    dir=$(dirname "$mdfile")
    grep "!\[" "$mdfile" | sed 's/.*](\(.*\)).*/\1/' | while read imgpath; do
        fullpath="$dir/$imgpath"
        if [ ! -f "$fullpath" ]; then
            echo "MISSING: $fullpath in $mdfile"
        fi
    done
done

# 2. Convert unsupported formats
for img in *.webp *.svg; do
    if [ -f "$img" ]; then
        convert "$img" "${img%.*}.png"  # ImageMagick
    fi
done

# 3. Use absolute paths in markdown or copy to working dir
```

**Python Helper for Image Path Resolution:**

```python
import re
from pathlib import Path
import shutil

def resolve_markdown_images(md_content, md_file_path, output_dir):
    """
    Convert relative image paths to absolute and copy images to output dir.
    Returns modified markdown content.
    """
    md_dir = Path(md_file_path).parent
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Pattern: ![alt](path) or ![alt](path "title")
    img_pattern = r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)'
    
    def replace_path(match):
        alt_text = match.group(1)
        img_path = match.group(2)
        
        # Resolve absolute path
        if not img_path.startswith(('http://', 'https://', '/')):
            abs_path = md_dir / img_path
            if abs_path.exists():
                # Copy to output dir with unique name
                new_name = f"{md_dir.stem}_{abs_path.name}"
                dest = output_path / new_name
                shutil.copy2(abs_path, dest)
                return f'![{alt_text}]({new_name})'
        
        return match.group(0)
    
    return re.sub(img_pattern, replace_path, md_content)
```

### Footer/Header Preservation

**Problem**: Pandoc with `--reference-doc` sometimes:
- Strips custom headers/footers from template
- Replaces with default pandoc headers
- Loses page numbering and branding

**Solution - Two-Stage Process:**

```python
from docx import Document

def preserve_headers_footers(template_path, content_path, output_path):
    """
    Merge content DOCX with template's headers/footers.
    """
    # Load template to extract headers/footers
    template = Document(template_path)
    
    # Load content (from pandoc conversion)
    content = Document(content_path)
    
    # Copy headers from template to content
    for i, section in enumerate(content.sections):
        if i < len(template.sections):
            template_section = template.sections[i]
            
            # Copy header
            if template_section.header:
                for para in template_section.header.paragraphs:
                    new_para = section.header.paragraphs[0]._element
                    new_para.getparent().remove(new_para)
                    section.header._element.append(copy.deepcopy(para._element))
            
            # Copy footer
            if template_section.footer:
                for para in template_section.footer.paragraphs:
                    new_para = section.footer.paragraphs[0]._element
                    new_para.getparent().remove(new_para)
                    section.footer._element.append(copy.deepcopy(para._element))
    
    content.save(output_path)
```

**Alternative - Direct XML Preservation:**

```python
def copy_section_properties(source_doc, target_doc):
    """
    Copy section properties including headers/footers at XML level.
    """
    from lxml import etree
    
    W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    
    # Get sectPr from source (template)
    source_body = source_doc.element.body
    source_sectPr = source_body.find(f'.//{W_NS}sectPr')
    
    # Get sectPr from target (content)
    target_body = target_doc.element.body
    target_sectPr = target_body.find(f'.//{W_NS}sectPr')
    
    if source_sectPr is not None and target_sectPr is not None:
        # Copy headerReference and footerReference elements
        for ref_type in ['headerReference', 'footerReference']:
            for source_ref in source_sectPr.findall(f'{W_NS}{ref_type}'):
                # Remove existing refs in target
                for target_ref in target_sectPr.findall(f'{W_NS}{ref_type}'):
                    target_sectPr.remove(target_ref)
                # Add source refs
                target_sectPr.append(copy.deepcopy(source_ref))
```

### Post-Conversion Verification

**Image Verification:**

```python
def verify_docx_images(docx_path):
    """
    Check that all images are properly embedded in DOCX.
    Returns list of missing/broken images.
    """
    doc = Document(docx_path)
    issues = []
    
    # Count image relationships
    image_count = 0
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            image_count += 1
            # Verify image data exists
            try:
                image_part = doc.part.related_parts[rel.rId]
                if not image_part.blob:
                    issues.append(f"Empty image blob: {rel.target_ref}")
            except Exception as e:
                issues.append(f"Cannot access image {rel.target_ref}: {e}")
    
    print(f"Total images found: {image_count}")
    
    # Check paragraphs for image references
    for i, para in enumerate(doc.paragraphs):
        for run in para.runs:
            # Check for drawing elements
            drawing_elements = run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing')
            if drawing_elements:
                for drawing in drawing_elements:
                    # Verify blip (image reference) exists
                    blip = drawing.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
                    if blip is None:
                        issues.append(f"Para {i}: Drawing without blip (broken image)")
    
    return issues
```

**Header/Footer Verification:**

```python
def verify_headers_footers(docx_path, expected_header_text=None, expected_footer_text=None):
    """
    Verify headers and footers are present and contain expected content.
    """
    doc = Document(docx_path)
    issues = []
    
    for i, section in enumerate(doc.sections):
        # Check header exists
        if not section.header:
            issues.append(f"Section {i}: Missing header")
        elif expected_header_text:
            header_text = section.header.paragraphs[0].text if section.header.paragraphs else ""
            if expected_header_text not in header_text:
                issues.append(f"Section {i}: Header missing expected text '{expected_header_text}'")
        
        # Check footer exists
        if not section.footer:
            issues.append(f"Section {i}: Missing footer")
        elif expected_footer_text:
            footer_text = section.footer.paragraphs[0].text if section.footer.paragraphs else ""
            if expected_footer_text not in footer_text:
                issues.append(f"Section {i}: Footer missing expected text '{expected_footer_text}'")
    
    return issues
```

### Complete Conversion Pipeline

```bash
#!/bin/bash
# complete-md-to-docx.sh

MD_FILE=$1
TEMPLATE=$2
OUTPUT=$3

# Stage 1: Prepare images
WORKDIR=$(mktemp -d)
python3 << 'PYEOF'
import sys
from pathlib import Path
md_file = Path("$MD_FILE")
work_dir = Path("$WORKDIR")

# Read and process markdown
content = md_file.read_text()
processed = resolve_markdown_images(content, md_file, work_dir)
(work_dir / "input.md").write_text(processed)

# Copy all referenced images
for img in md_file.parent.glob("**/*.png"):
    if img.name not in [f.name for f in work_dir.iterdir()]:
        shutil.copy(img, work_dir)
PYEOF

# Stage 2: Pandoc conversion
pandoc "$WORKDIR/input.md" \
    --reference-doc="$TEMPLATE" \
    --resource-path="$WORKDIR" \
    -o "$WORKDIR/pandoc-output.docx"

# Stage 3: Post-process (preserve headers/footers)
python3 << 'PYEOF'
from docx import Document
import copy

template = Document("$TEMPLATE")
content = Document("$WORKDIR/pandoc-output.docx")

# Copy headers/footers
for i, section in enumerate(content.sections):
    if i < len(template.sections):
        template_section = template.sections[i]
        
        # Copy header content
        if template_section.header and section.header:
            section.header.paragraphs[0].text = template_section.header.paragraphs[0].text
            # Copy runs for formatting
            for run in template_section.header.paragraphs[0].runs[1:]:
                new_run = section.header.paragraphs[0].add_run(run.text)
                new_run.bold = run.bold
                new_run.italic = run.italic
                new_run.font.size = run.font.size
        
        # Copy footer content
        if template_section.footer and section.footer:
            section.footer.paragraphs[0].text = template_section.footer.paragraphs[0].text

content.save("$OUTPUT")
PYEOF

# Stage 4: Verification
python3 << 'PYEOF'
issues = verify_docx_images("$OUTPUT")
issues += verify_headers_footers("$OUTPUT", expected_footer_text="EC-Council")

if issues:
    print("VERIFICATION FAILED:")
    for issue in issues:
        print(f"  - {issue}")
    exit(1)
else:
    print("VERIFICATION PASSED")
PYEOF

rm -rf "$WORKDIR"
```

### Quick Verification Commands

```bash
# Check image count
echo "Images in DOCX:"
unzip -l document.docx | grep -c "media/"

# Check header/footer XML
echo "Headers:"
unzip -p document.docx word/header1.xml | grep -o '<w:t[^>]*>[^<]*</w:t>' | head -5

echo "Footers:"
unzip -p document.docx word/footer1.xml | grep -o '<w:t[^>]*>[^<]*</w:t>' | head -5

# Visual check
libreoffice --headless --convert-to pdf document.docx
pdftoppm -png -r 150 document.pdf page
# Inspect page-01.png for header/footer visibility
```

---

# PART 3: SANITATION RULES

## Artifact Removal (Both PPTX and DOCX)

```python
for para in doc.paragraphs:  # or slide shapes
    for run in para.runs:
        for tok in ['***', '**', '__', '---']:
            run.text = run.text.replace(tok, '')
```

## Forbidden Operations

| Operation | Why |
|-----------|-----|
| `text_frame.clear()` | Destroys all paragraph/run formatting |
| `text_frame.text = "..."` | Replaces entire frame, loses runs |
| `shape.left = ...` | Moves shape, breaks template layout |
| `add_slide()` without cloning | Creates blank slide without background |
| `deepcopy(slide)` directly | Breaks package relationships |
| Pandoc for PPTX precision | Rebuilds slides, loses complex layouts |

---

# PART 4: TOOLS REFERENCE

## Recommended Stack

| Tool | Role | Required |
|------|------|----------|
| `python-pptx` >= 1.0.2 | PPTX clone + inject | Yes |
| `python-docx` >= 1.1.2 | DOCX element construction | Yes |
| `lxml` | XML manipulation for slide cloning | Yes |
| `libreoffice` (headless) | PDF conversion for verification | Yes |
| `pdftoppm` (poppler-utils) | PDF to PNG for visual checks | Yes |

## Alternative Tools (When Primary Fails)

| Tool | Use Case |
|------|----------|
| `Pandoc` + `--reference-doc` | Quick DOCX generation (less control) |
| `AutoPPTX` | JSON-driven PPTX placeholder replacement |
| `docxtpl` | Jinja2 templating for DOCX |
| `Aspose.Slides FOSS` | Better slide cloning API |

## CLI Commands

```bash
# Verify PPTX
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.pptx
pdftoppm -png -r 150 /tmp/verify/output.pdf /tmp/slides/slide

# Verify DOCX
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.docx
pdftoppm -png -r 150 -f 1 -l 5 /tmp/verify/output.pdf /tmp/pages/page

# Check for markdown artifacts in PPTX text
python3 -c "
from pptx import Presentation
prs = Presentation('output.pptx')
for i, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.has_text_frame:
            for p in shape.text_frame.paragraphs:
                for r in p.runs:
                    if any(a in r.text for a in ['***','**','__','---']):
                        print(f'Slide {i+1}: artifact in \"{r.text[:50]}\"')
"
```

---

# PART 5: COMPLETE WORKFLOW

## For a New Section's Slides

1. **Analyze template** with the template analysis script (Section 1.5)
2. **Read video scripts** for the section
3. **Create slides markdown** file mapping content to template slide types
4. **Run generator script** (`generate_section_pptx_v3.py`)
5. **Verify output** with LibreOffice PDF + pdftoppm visual check
6. **Fix any issues** (text not replaced, backgrounds missing)
7. **Save final PPTX** in `slides-output/`

## For the Course eBook DOCX

1. **Ensure CLEAN DOCX exists** (built from chapter markdown files)
2. **Run ebook generator** (`generate_final_ebook.py`)
3. **Verify output** with LibreOffice PDF + visual check
4. **Confirm** EC-Council branding (footer, colors, fonts)

---

# PART 6: EDGE CASES AND COMPLEX TEMPLATES

## 6.1 EC-Council COV (Course Overview) Template

The COV template has fundamentally different structure than section templates. It uses **TextBox shapes** instead of standard placeholders, and includes **complex diagram slides** with interconnected shapes.

### Key Differences from Section Templates

| Aspect | Section Template | COV Template |
|--------|-----------------|--------------|
| Title element | Placeholder (type 1) | TextBox named "TextBox 9" |
| Body content | Multi-run placeholders | Text boxes with "SECTION NAME" pattern |
| Roadmap slide | Simple layout | Complex diagram with 7+ grouped shapes |
| Shape types | AUTO_SHAPE, PLACEHOLDER | FREEFORM, GROUP, TEXT_BOX |

### COV Template Layouts

```
Slide 0: Full Image (Title slide)
  - Static background with title area
  
Slide 1-2: NSPPPT0013 (Synopsis layout)
  - TextBox 9: Title (not a placeholder!)
  - TextBox 10: "SECTION NAME" + description
  
Slide 3: NSPPPT008 (Two-column with image)
  - Title Placeholder
  - Rectangle: Bullet points
  
Slide 4: NSPPPT008 (Prerequisites variant)
  - Same as Slide 3
  
Slide 5: Blank (Target audience)
  - Title placeholder only
  
Slide 6: NSPPPT0013 (Closing slide)
  - Same structure as Slides 1-2
```

### Roadmap Diagram Handling (Critical Edge Case)

The roadmap slide (template index 2) contains a **complex diagram** with:
- 7 numbered nodes (shapes with numbers 1-7)
- 7 text boxes with "SECTION NAME" pattern
- Connecting lines and arrows (Grouped shapes)
- Visual grid layout (position-dependent ordering)

**Detection Strategy:**

```python
def find_text_boxes_with_pattern(slide, pattern):
    """Find text boxes by content pattern, not placeholder type."""
    matches = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text
            if pattern in text:  # "SECTION NAME" in COV template
                matches.append(shape)
    return matches

# Sort by vertical position to maintain visual order
section_boxes.sort(key=lambda s: s.top if hasattr(s, 'top') else 0)
```

**Content Injection for Roadmap:**

```python
def set_section_text_boxes(slide, section_contents):
    """
    COV roadmap has 7 text boxes with:
    - Run 0: "SECTION NAME" (to be replaced with section title)
    - Run 1: Description text (multiline in some cases)
    """
    section_boxes = find_text_boxes_with_pattern(slide, "SECTION NAME")
    section_boxes.sort(key=lambda s: s.top)  # Visual order
    
    for shape, content in zip(section_boxes, section_contents):
        tf = shape.text_frame
        if tf.paragraphs and tf.paragraphs[0].runs:
            # First run gets the title
            tf.paragraphs[0].runs[0].text = content['title']
            
            # Second run gets description
            if len(tf.paragraphs[0].runs) > 1:
                tf.paragraphs[0].runs[1].text = content['description']
```

### Synopsis Slide Title Handling

COV "Synopsis" slides use TextBox for titles, NOT placeholders:

```python
def set_synopsis_title(slide, new_title):
    """
    COV template stores title in TextBox 9, not a placeholder.
    Must search by shape name or existing "Synopsis" text.
    """
    # Method 1: By shape name
    for shape in slide.shapes:
        if shape.name == 'TextBox 9':
            shape.text_frame.paragraphs[0].runs[0].text = new_title
            return True
    
    # Method 2: Fallback - search for "Synopsis" text
    for shape in slide.shapes:
        if shape.has_text_frame and 'Synopsis' in shape.text_frame.text:
            for run in shape.text_frame.paragraphs[0].runs:
                if 'Synopsis' in run.text:
                    run.text = run.text.replace('Synopsis', new_title)
                    return True
    return False
```

### Complete COV Generation Workflow

```python
def generate_cov_pptx():
    """COV template requires different handling per slide type."""
    prs = Presentation('COV_Template.pptx')
    
    # Slide 1: Title (Full Image) - uses standard placeholder
    slide1 = duplicate_slide(prs, 0)
    set_title_placeholder(slide1, "Course Title")
    
    # Slide 2-3: Synopsis - uses TextBox for title
    slide2 = duplicate_slide(prs, 1)
    set_synopsis_title(slide2, "Author Introduction")  # Special handler
    set_simple_text_box(slide2, "SECTION NAME", "Author Name")
    
    # Slide 4: Roadmap - complex diagram
    slide4 = duplicate_slide(prs, 2)
    set_title_placeholder(slide4, "Course Roadmap")  # This one has placeholder
    section_contents = [
        {'title': 'SECTION 1', 'description': 'Description here'},
        # ... 7 items
    ]
    set_section_text_boxes(slide4, section_contents)  # Pattern-based injection
    
    # Slides 5-6: NSPPPT008 - Rectangle with bullets
    slide5 = duplicate_slide(prs, 3)
    set_title_placeholder(slide5, "Prerequisites")
    set_rectangle_points(slide5, ["Point 1", "Point 2", "Point 3"])
```

## 6.2 Complex Diagram Slides (General Pattern)

When templates contain **flowcharts, roadmaps, or infographics**:

### Detection Rules

```python
def is_complex_diagram_slide(slide):
    """Detect slides with complex visual structures."""
    group_count = sum(1 for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.GROUP)
    freeform_count = sum(1 for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.FREEFORM)
    
    # Complex diagrams have many grouped/interconnected shapes
    return group_count > 3 or freeform_count > 5
```

### Handling Strategy

1. **Identify text containers**: Find shapes that hold editable text
2. **Pattern matching**: Use content patterns ("SECTION NAME", "Click to add", etc.)
3. **Position-based ordering**: Sort by (top, left) for visual sequence
4. **Run-level injection**: Preserve formatting in multi-run text frames
5. **Never move shapes**: Keep original positions to preserve layout

### Anti-Patterns to Avoid

| Bad Practice | Why It Fails | Correct Approach |
|--------------|--------------|------------------|
| `shape.left = x` | Breaks diagram layout | Keep original positions |
| `slide.shapes.add_textbox()` | Creates new shapes, duplicates existing | Modify existing shapes only |
| `text_frame.clear()` | Destroys paragraph structure | Modify runs in-place |
| Searching only by placeholder type | Misses TextBox-based titles | Search by shape name + content |
| Single-pass replacement | Misses multi-run text | Handle each run individually |

## 6.3 Template Analysis Script

Always analyze templates before generation:

```python
def analyze_template(pptx_path):
    """Required: Analyze any new template before content injection."""
    prs = Presentation(pptx_path)
    
    for i, slide in enumerate(prs.slides):
        print(f"\n=== SLIDE {i} ===")
        print(f"Layout: {slide.slide_layout.name}")
        
        for j, shape in enumerate(slide.shapes):
            print(f"\n  Shape {j}: {shape.name}")
            print(f"    Type: {shape.shape_type}")
            print(f"    Placeholder: {shape.is_placeholder}")
            
            if shape.is_placeholder:
                print(f"    PH Type: {shape.placeholder_format.type}")
            
            if shape.has_text_frame:
                text = shape.text_frame.text[:80]
                print(f"    Text: '{text}'")
                print(f"    Paragraphs: {len(shape.text_frame.paragraphs)}")
```

## 6.4 Verification for Complex Slides

```bash
# Visual check for complex slides
libreoffice --headless --convert-to pdf course-overview.pptx
pdftoppm -png -r 200 course-overview.pdf slide

# Check specific slides with diagrams
# Open slide-004.png (roadmap slide) and verify:
# - All 7 section boxes have correct text
# - Numbers 1-7 are visible
# - Connecting lines preserved
# - No text overflow or misalignment
```

---

# NON-NEGOTIABLE RULES

1. If a method risks layout drift, style loss, markdown leakage, or file corruption, it MUST NOT be used.
2. Only surgical, in-place modification and verified pipelines are allowed.
3. Every generated file MUST pass visual verification before being considered complete.
4. No markdown artifacts may remain in any final document.
5. Template backgrounds, fonts, colors, and layout positions must be preserved exactly.
