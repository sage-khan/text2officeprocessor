"""
scripts/create_bundled_templates.py

Generates the bundled generic templates shipped with text2officeprocessor.

Run once from the project root:
    python scripts/create_bundled_templates.py

Outputs:
    templates/generic-slides.pptx   — 13-slide template bank
    templates/generic-document.docx — plain branded document template

These files are committed to the repo and included in the PyPI package.
They give new users a working template without needing their own file.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt, Emu

from docx import Document
from docx.shared import Pt as DocxPt, RGBColor as DocxRGB, Inches as DocxInches
from docx.enum.style import WD_STYLE_TYPE

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

PPTX_OUT = TEMPLATES_DIR / "generic-slides.pptx"
DOCX_OUT = TEMPLATES_DIR / "generic-document.docx"

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

DARK_BLUE = RGBColor(0x1A, 0x37, 0x6C)       # #1A376C
ACCENT = RGBColor(0x00, 0x7A, 0xC2)           # #007AC2
LIGHT_GREY = RGBColor(0xF4, 0xF4, 0xF4)      # #F4F4F4
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK_TEXT = RGBColor(0x1A, 0x1A, 0x2E)       # #1A1A2E

SLIDE_WIDTH = Inches(13.33)
SLIDE_HEIGHT = Inches(7.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_text_box(slide, left, top, width, height, text, font_size,
                  bold=False, color=DARK_TEXT, align=PP_ALIGN.LEFT, italic=False):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txBox


def _fill_shape(shape, color: RGBColor):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def _add_rect(slide, left, top, width, height, color: RGBColor):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    _fill_shape(shape, color)
    shape.line.fill.background()
    return shape


# ---------------------------------------------------------------------------
# PPTX — 13 slide template bank
# ---------------------------------------------------------------------------

def build_pptx() -> None:
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    blank_layout = prs.slide_layouts[6]  # completely blank

    slides_spec = [
        _slide_section_header,
        _slide_video_title,
        _slide_single_point,
        _slide_multi_point,
        _slide_callout,
        _slide_stats,
        _slide_key_pointers,
        _slide_key_highlights,
        _slide_image_left,
        _slide_features,
        _slide_benefits,
        _slide_excellence_grid,
        _slide_next_video,
    ]

    for builder in slides_spec:
        slide = prs.slides.add_slide(blank_layout)
        builder(slide)

    prs.save(str(PPTX_OUT))
    print(f"  Created: {PPTX_OUT}  ({PPTX_OUT.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Individual slide builders
# Each function injects a background + placeholder text that matches the
# strings declared in config/default_rules.yaml placeholder_map.
# ---------------------------------------------------------------------------

def _bg(slide, bg_color=DARK_BLUE, accent_color=ACCENT):
    """Standard dark background with accent strip."""
    _add_rect(slide, 0, 0, SLIDE_WIDTH, SLIDE_HEIGHT, bg_color)
    _add_rect(slide, 0, SLIDE_HEIGHT - Inches(0.08), SLIDE_WIDTH, Inches(0.08), accent_color)


def _slide_section_header(slide):
    _bg(slide)
    _add_rect(slide, 0, 0, Inches(0.12), SLIDE_HEIGHT, ACCENT)
    _add_text_box(slide, Inches(0.5), Inches(1.5), Inches(12), Inches(2),
                  "Section Name Here", 54, bold=True, color=WHITE, align=PP_ALIGN.LEFT)
    _add_text_box(slide, Inches(0.5), Inches(3.8), Inches(6), Inches(0.8),
                  "SECTION Number", 24, color=ACCENT, align=PP_ALIGN.LEFT)


def _slide_video_title(slide):
    _bg(slide)
    _add_text_box(slide, Inches(0.5), Inches(0.4), Inches(4), Inches(0.5),
                  "Section Name", 16, color=ACCENT)
    _add_text_box(slide, Inches(0.5), Inches(1.2), Inches(12), Inches(1.8),
                  "Video Name", 44, bold=True, color=WHITE)
    _add_text_box(slide, Inches(0.5), Inches(3.2), Inches(3), Inches(0.5),
                  "Video Number", 18, color=LIGHT_GREY)


def _slide_single_point(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "SINGLE POINT SLIDE", 28, bold=True, color=WHITE)
    _add_text_box(slide, Inches(0.8), Inches(1.5), Inches(11.5), Inches(4.5),
                  "This is a sample text", 22, color=DARK_TEXT)


def _slide_multi_point(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "Multi Point Slide", 28, bold=True, color=WHITE)
    for i, placeholder in enumerate(["Bullet point one", "Bullet point two", "Bullet point three"]):
        _add_text_box(slide, Inches(0.9), Inches(1.4 + i * 0.8), Inches(11), Inches(0.65),
                      f"• {placeholder}", 20, color=DARK_TEXT)


def _slide_callout(slide):
    _bg(slide)
    _add_rect(slide, Inches(1), Inches(1.5), Inches(11), Inches(4), ACCENT)
    _add_text_box(slide, Inches(1.4), Inches(2.0), Inches(10.2), Inches(3),
                  "A key point (or issue)!", 36, bold=True, color=WHITE, align=PP_ALIGN.CENTER)


def _slide_stats(slide):
    _bg(slide)
    _add_text_box(slide, Inches(1), Inches(1.2), Inches(11), Inches(2.2),
                  "+80%", 96, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)
    _add_text_box(slide, Inches(1), Inches(3.8), Inches(11), Inches(1.2),
                  "That\u2019s how much", 28, color=WHITE, align=PP_ALIGN.CENTER)


def _slide_key_pointers(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "Key Pointers", 28, bold=True, color=WHITE)
    positions = [(0.4, 1.3), (6.8, 1.3), (0.4, 4.0), (6.8, 4.0)]
    for left, top in positions:
        _add_rect(slide, Inches(left), Inches(top), Inches(5.8), Inches(2.4), WHITE)
        _add_text_box(slide, Inches(left + 0.15), Inches(top + 0.15), Inches(5.5), Inches(2.0),
                      "Pointer title\nDescription text here", 16, color=DARK_TEXT)


def _slide_key_highlights(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.3), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.15), Inches(8), Inches(0.7),
                  "Key Highlights", 30, bold=True, color=WHITE)
    _add_text_box(slide, Inches(0.5), Inches(0.85), Inches(8), Inches(0.4),
                  "Enter your subhead line here", 16, color=LIGHT_GREY)
    card_width = Inches(3.0)
    card_height = Inches(4.5)
    for i in range(4):
        left = Inches(0.3 + i * 3.25)
        _add_rect(slide, left, Inches(1.5), card_width, card_height, WHITE)
        _add_text_box(slide, left + Inches(0.15), Inches(1.65), card_width - Inches(0.3), Inches(0.6),
                      f"card_{i+1}_title", 18, bold=True, color=DARK_BLUE)
        _add_text_box(slide, left + Inches(0.15), Inches(2.35), card_width - Inches(0.3), Inches(3.4),
                      f"card_{i+1}_body", 14, color=DARK_TEXT)


def _slide_image_left(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "Image Left Slide", 28, bold=True, color=WHITE)
    _add_rect(slide, Inches(0.3), Inches(1.3), Inches(5.5), Inches(5.5), LIGHT_GREY)
    _add_text_box(slide, Inches(0.3), Inches(3.5), Inches(5.5), Inches(0.6),
                  "[Image placeholder]", 14, color=DARK_BLUE, align=PP_ALIGN.CENTER, italic=True)
    _add_text_box(slide, Inches(6.2), Inches(1.4), Inches(6.8), Inches(5.0),
                  "Image caption or body text goes here", 20, color=DARK_TEXT)


def _slide_features(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "Features", 28, bold=True, color=WHITE)
    for i in range(6):
        col = i % 3
        row = i // 3
        left = Inches(0.4 + col * 4.3)
        top = Inches(1.3 + row * 2.8)
        _add_rect(slide, left, top, Inches(3.9), Inches(2.4), WHITE)
        _add_text_box(slide, left + Inches(0.15), top + Inches(0.15), Inches(3.6), Inches(2.1),
                      f"Feature {i+1}", 16, bold=True, color=DARK_BLUE)


def _slide_benefits(slide):
    _bg(slide, LIGHT_GREY, ACCENT)
    _add_rect(slide, 0, 0, SLIDE_WIDTH, Inches(1.1), DARK_BLUE)
    _add_text_box(slide, Inches(0.5), Inches(0.2), Inches(12), Inches(0.7),
                  "Benefits", 28, bold=True, color=WHITE)
    for i in range(6):
        top = Inches(1.3 + i * 0.95)
        _add_rect(slide, Inches(0.4), top, Inches(0.55), Inches(0.65), ACCENT)
        _add_text_box(slide, Inches(1.1), top, Inches(11.5), Inches(0.65),
                      f"Benefit item {i+1} description goes here", 18, color=DARK_TEXT)


def _slide_excellence_grid(slide):
    _bg(slide)
    _add_text_box(slide, Inches(0.5), Inches(0.4), Inches(12), Inches(1.0),
                  "EXCELLENCE IN THE", 36, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    for i in range(3):
        left = Inches(0.6 + i * 4.2)
        _add_rect(slide, left, Inches(1.8), Inches(3.8), Inches(4.8), ACCENT)
        _add_text_box(slide, left + Inches(0.2), Inches(2.0), Inches(3.4), Inches(0.7),
                      f"item_0{i+1}_title", 20, bold=True, color=WHITE)
        _add_text_box(slide, left + Inches(0.2), Inches(2.8), Inches(3.4), Inches(3.4),
                      f"item_0{i+1}_body", 16, color=WHITE)


def _slide_next_video(slide):
    _bg(slide)
    _add_text_box(slide, Inches(0.5), Inches(0.5), Inches(4), Inches(0.5),
                  "Next Video", 18, color=ACCENT)
    _add_text_box(slide, Inches(0.5), Inches(1.5), Inches(12), Inches(2),
                  "Name of the Next Video", 44, bold=True, color=WHITE)


# ---------------------------------------------------------------------------
# DOCX — plain branded document template
# ---------------------------------------------------------------------------

def build_docx() -> None:
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = DocxInches(1.0)
        section.bottom_margin = DocxInches(1.0)
        section.left_margin = DocxInches(1.2)
        section.right_margin = DocxInches(1.2)

    # Normal style
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = DocxPt(11)
    normal.font.color.rgb = DocxRGB(0x1A, 0x1A, 0x2E)

    # Heading 1
    h1 = doc.styles["Heading 1"]
    h1.font.name = "Calibri"
    h1.font.size = DocxPt(24)
    h1.font.bold = True
    h1.font.color.rgb = DocxRGB(0x1A, 0x37, 0x6C)

    # Heading 2
    h2 = doc.styles["Heading 2"]
    h2.font.name = "Calibri"
    h2.font.size = DocxPt(18)
    h2.font.bold = True
    h2.font.color.rgb = DocxRGB(0x00, 0x7A, 0xC2)

    # Heading 3
    h3 = doc.styles["Heading 3"]
    h3.font.name = "Calibri"
    h3.font.size = DocxPt(14)
    h3.font.bold = True
    h3.font.color.rgb = DocxRGB(0x1A, 0x37, 0x6C)

    # List Bullet style
    try:
        lb = doc.styles["List Bullet"]
        lb.font.name = "Calibri"
        lb.font.size = DocxPt(11)
    except KeyError:
        pass

    # Placeholder content that will be replaced at render time
    doc.add_heading("Document Title", level=1)
    doc.add_paragraph(
        "This is the introduction paragraph. Replace this with your content."
    )

    doc.save(str(DOCX_OUT))
    print(f"  Created: {DOCX_OUT}  ({DOCX_OUT.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Building bundled templates...")
    build_pptx()
    build_docx()
    print("Done.")
