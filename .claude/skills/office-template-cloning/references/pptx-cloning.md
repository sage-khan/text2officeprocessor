# PPTX: SlidePart Clone + Inject

## Why Other Methods Fail

| Method | Problem |
|--------|---------|
| `add_slide(layout)` + shape copy | Loses background images, breaks Picture Placeholders |
| `copy.deepcopy(slide)` | Breaks internal relationships, corrupts package |
| Pandoc `--reference-doc` | Rebuilds slides from scratch, loses complex layouts |
| `add_slide(layout)` alone | Only gets layout structure, no slide-specific content |

## The Working Clone Function (python-pptx 1.0.2+)

```python
import copy, re
from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import PackURI
from pptx.parts.slide import SlidePart

def duplicate_slide(prs, slide_index):
    """Clone a template slide preserving backgrounds, images, and all formatting."""
    source_slide = prs.slides[slide_index]
    source_part = source_slide.part

    new_xml = copy.deepcopy(source_part._element)

    nums = []
    for s in prs.slides:
        m = re.search(r'slide(\d+)', str(s.part.partname))
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums) + 1 if nums else 1
    new_partname = PackURI(f'/ppt/slides/slide{next_num}.xml')

    new_part = SlidePart(new_partname, source_part.content_type, prs.part.package, new_xml)

    for rel_key in source_part.rels:
        rel = source_part.rels[rel_key]
        new_part.rels.get_or_add(rel.reltype, rel._target)

    rId = prs.part.relate_to(new_part, RT.SLIDE)

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

**Critical notes on the `SlidePart` constructor:**
- Signature: `SlidePart(partname, content_type, package, element)` — **positional only**.
- `package` = `prs.part.package` (NOT `source_part.package`).
- `element` = the deep-copied lxml `Element` (NOT bytes, NOT a blob — `XmlPart.__init__`
  expects `element`; `Part.__init__` expects `blob`; mixing them up is the #1 source of
  cryptic constructor errors here).

## Removing Template Bank Slides

After cloning all content slides, remove the originals:

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

## Text Replacement (3-Layer Strategy)

Curly quotes (`‘’“”`) are common in template text but not in markdown —
**always normalize both sides** before comparing:

```python
def _normalize(text):
    return (text.replace('‘', "'").replace('’', "'")
                .replace('“', '"').replace('”', '"'))
```

**Layer 1 — single-run match (most common):**

```python
for ridx, run in enumerate(paragraph.runs):
    if old_norm in _normalize(run.text):
        run.text = _normalize(run.text).replace(old_norm, new_text)
        # Replacement consumed the whole run? Blank everything after it —
        # otherwise a two-run title like "EXCELLENCE IN THE"+"MAKING" leaves "MAKING" dangling.
        if _normalize(run.text.strip()) == new_text.strip():
            for r in paragraph.runs[ridx + 1:]:
                r.text = ""
        break
```

**Layer 2 — cross-run match** (old text spans multiple runs in one paragraph, e.g.
`run[0]="That"` + `run[1]="'s how much"`):

```python
full_text = "".join(run.text for run in paragraph.runs)
if old_norm in _normalize(full_text):
    paragraph.runs[0].text = _normalize(full_text).replace(old_norm, new_text)
    for run in paragraph.runs[1:]:
        run.text = ""
```

Common patterns you'll hit: numbered placeholder variants ("Key Element Title 01" — match
on the prefix), and generic body placeholders ("This is a sample text. You simply add..." —
match on a distinctive substring like "sample text").

---

## Template-Aware Image Injection (Slot Detection + Crop-to-Fit)

Never `add_picture()` at guessed coordinates — find the slide's actual image slot, then
crop the source image to the slot's aspect ratio so it fills it exactly with no distortion.

**Detect the slot** — two patterns exist; prefer the tighter-fitting if both match:

- **Pattern A:** native picture placeholder (`shape.placeholder_format.type ==
  PP_PLACEHOLDER.PICTURE`, inherited from the layout).
- **Pattern B:** a text shape standing in for an image, matching a pattern like
  `[Image placeholder]`, `Photo here`, `(Insert picture)`. Its bounding box is the slot —
  and the label shape **must be removed** after injection or it overlays the picture.

```python
import re
_IMAGE_PLACEHOLDER_RE = re.compile(r'\[image placeholder\]|photo here|insert picture', re.I)

def find_image_slot(slide):
    candidates = []
    for shape in slide.shapes:
        if shape.is_placeholder and shape.placeholder_format.type == PP_PLACEHOLDER.PICTURE:
            candidates.append(shape)
        elif shape.has_text_frame and _IMAGE_PLACEHOLDER_RE.search(shape.text_frame.text):
            candidates.append(shape)
    if not candidates:
        return None
    return min(candidates, key=lambda s: s.width * s.height)  # most specific match
```

**Crop to aspect (cover-fit) with PIL, then embed at the slot's exact box:**

```python
from PIL import Image

def _crop_to_aspect(image_path, target_w, target_h, out_path):
    img = Image.open(image_path)
    src_ratio, dst_ratio = img.width / img.height, target_w / target_h
    if src_ratio > dst_ratio:        # source too wide — crop left/right
        new_w = int(img.height * dst_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    elif src_ratio < dst_ratio:      # source too tall — crop top/bottom
        new_h = int(img.width / dst_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    img.save(out_path)
    return out_path

def inject_template_image(slide, image_path, slide_number):
    slot = find_image_slot(slide)
    if slot is None:
        return False
    cropped = _crop_to_aspect(image_path, slot.width, slot.height, f'/tmp/cropped_{slide_number}.png')
    slide.shapes.add_picture(cropped, slot.left, slot.top, slot.width, slot.height)
    slot._element.getparent().remove(slot._element)   # drop the now-redundant label/placeholder
    return True
```

| Approach | Problem |
|----------|---------|
| `add_picture(path, Inches(x), Inches(y))` at guessed coords | Overlays template content |
| Embedding without cropping | Distorted/stretched or letterboxed images |
| Leaving the placeholder/label shape in place | Label text overlays the picture |
| Centring on the whole slide | Only correct for full-bleed diagram slides — wrong for a defined picture slot |

---

## Tabular Content in PPTX — There Is No Safe Native Recipe

PowerPoint table shapes (`graphicFrame`/`tbl`) are layout-fragile and outside any cloned
slide's design system. When source content is tabular:

1. **Prefer an existing grid/comparison layout** (e.g. "Key Highlights 4-col") — map rows
   onto card title/body slots via the cross-run replace above.
2. **Or flatten to bullets**: `"Metric: Value"` per line on a multi-point slide.
3. **Never** `slide.shapes.add_table()` on a cloned content slide.

If a template genuinely needs in-slide tables, that's a new recipe to build and visually
verify (the same way `inject_template_image` was) — don't let an LLM "decide" to add a
table shape based on guesswork; see [layout-manifest.md](layout-manifest.md) for how
manifests keep this constrained to *proven* recipes only.

---

## Diagram Slides (`.drawio` / static images, full-bleed)

For dedicated diagram slides (not content-with-image-slot), convert `.drawio` → PNG and
centre it on the slide with margins, preserving aspect ratio:

```python
MARGIN = Inches(0.5)
# compute width/height to fit within (slide_width - 2*MARGIN, slide_height - 2*MARGIN)
# preserving aspect ratio, then centre: left = (slide_width - pic_width) / 2, etc.
slide.shapes.add_picture(png_path, left, top, width=pic_width, height=pic_height)
```

This is the right tool for full-bleed/diagram slides specifically — don't use it as a
substitute for slot-based injection on a content slide that has a defined picture
placeholder (you'll get the wrong visual result and the slot's label will linger).

---

## Forbidden Operations Recap

| Operation | Why |
|-----------|-----|
| `text_frame.clear()` | Destroys all paragraph/run formatting |
| `text_frame.text = "..."` | Replaces entire frame, loses runs |
| `shape.left = ...` | Moves shape, breaks template layout |
| `add_slide()` without cloning | Blank slide, no background |
| `deepcopy(slide)` directly | Breaks package relationships |
| Pandoc for PPTX precision work | Rebuilds slides, loses complex layouts |

## Verification Checklist

```bash
libreoffice --headless --convert-to pdf --outdir /tmp/verify output.pptx
mkdir -p /tmp/slide-images
pdftoppm -png -r 150 /tmp/verify/output.pdf /tmp/slide-images/slide
ls -la /tmp/slide-images/   # <50KB = missing background; 200-500KB = background preserved
```

Then **look at the rendered PNGs** (Read tool or open them) and check: titles fully
replaced (no dangling run remnants), bullets/cards all populated, images filling their
slots without distortion or label overlay, no markdown artifacts (`**`, `__`, `---`)
anywhere — especially inside any text that came from a table-flattening fallback.
