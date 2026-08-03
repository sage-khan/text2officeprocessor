"""
Style Extractor — reads DOCX/PPTX templates and produces an ExtractedStyleSheet.

Inspired by edgemint's extract/document.py but extended for PPTX support.
The extracted data enables:
- Template analysis (``text2officeprocessor analyze-template``)
- Style-aware generation (Pandoc reference.docx)
- Template diffing and version tracking
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

from src.core.exceptions import TemplateNotFoundError
from src.core.extraction.models import (
    DocxStyle,
    ExtractedStyleSheet,
    FontProperties,
    NumberingDef,
    NumberingLevel,
    ParagraphFormat,
    PlaceholderInfo,
    PptxSlideLayout,
    SectionProperties,
    ThemeInfo,
)

logger = logging.getLogger(__name__)

# OOXML namespaces
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

_NSMAP = {
    "w": _W,
    "a": _A,
    "r": _R,
    "p": _P,
}

# EMU conversion constants
_EMU_PER_PT = 12700
_TWIPS_PER_PT = 20.0
_HALF_PT = 2.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_styles(template_path: Path) -> ExtractedStyleSheet:
    """
    Auto-detect template type and extract styles.

    Args:
        template_path: Path to a .docx or .pptx file.

    Returns:
        ExtractedStyleSheet with full visual identity.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise TemplateNotFoundError(f"Template not found: {template_path}")

    suffix = template_path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_styles(template_path)
    elif suffix == ".pptx":
        return extract_pptx_styles(template_path)
    else:
        raise TemplateNotFoundError(
            f"Unsupported template format '{suffix}'. Use .docx or .pptx."
        )


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def extract_docx_styles(docx_path: Path) -> ExtractedStyleSheet:
    """
    Extract the complete visual identity from a DOCX template.

    Reads styles.xml, theme1.xml, numbering.xml, and document.xml section props.
    """
    docx_path = Path(docx_path)
    parts: dict[str, bytes] = {}

    target_parts = [
        "word/styles.xml",
        "word/theme/theme1.xml",
        "word/numbering.xml",
        "word/document.xml",
    ]

    with ZipFile(docx_path) as archive:
        for name in target_parts:
            if name in archive.namelist():
                parts[name] = archive.read(name)

    styles = _parse_docx_styles(parts.get("word/styles.xml"))
    theme = _parse_theme(parts.get("word/theme/theme1.xml"))
    numbering = _parse_docx_numbering(parts.get("word/numbering.xml"))
    section_props = _parse_docx_section_props(parts.get("word/document.xml"))

    logger.info(
        "Extracted from DOCX: %d styles, %d numbering defs",
        len(styles), len(numbering),
    )

    return ExtractedStyleSheet(
        format="docx",
        source_file=docx_path.name,
        extracted_at=ExtractedStyleSheet.timestamp(),
        styles=styles,
        numbering_defs=numbering,
        section_properties=section_props,
        theme=theme,
    )


def _parse_docx_styles(xml_bytes: bytes | None) -> list[DocxStyle]:
    """Parse w:styles from styles.xml."""
    if not xml_bytes:
        return []

    root = etree.fromstring(xml_bytes)
    results: list[DocxStyle] = []

    for style_el in root.findall(f"{{{_W}}}style"):
        style_id = style_el.get(f"{{{_W}}}styleId", "")
        style_type = style_el.get(f"{{{_W}}}type", "paragraph")

        name_el = style_el.find(f"{{{_W}}}name")
        name = name_el.get(f"{{{_W}}}val", style_id) if name_el is not None else style_id

        based_on_el = style_el.find(f"{{{_W}}}basedOn")
        based_on = based_on_el.get(f"{{{_W}}}val") if based_on_el is not None else None

        next_el = style_el.find(f"{{{_W}}}next")
        next_style = next_el.get(f"{{{_W}}}val") if next_el is not None else None

        is_default = style_el.get(f"{{{_W}}}default") == "1"

        # Extract run properties (font)
        rpr = style_el.find(f"{{{_W}}}rPr")
        font = _parse_run_props(rpr) if rpr is not None else None

        # Extract paragraph properties
        ppr = style_el.find(f"{{{_W}}}pPr")
        para_fmt = _parse_para_props(ppr) if ppr is not None else None

        results.append(DocxStyle(
            style_id=style_id,
            name=name,
            style_type=style_type,
            based_on=based_on,
            next_style=next_style,
            is_default=is_default,
            font=font,
            paragraph_format=para_fmt,
        ))

    return results


def _parse_run_props(rpr: Any) -> FontProperties:
    """Extract FontProperties from a w:rPr element."""
    font = FontProperties()

    # Font name
    rfonts = rpr.find(f"{{{_W}}}rFonts")
    if rfonts is not None:
        font.name = (
            rfonts.get(f"{{{_W}}}ascii")
            or rfonts.get(f"{{{_W}}}hAnsi")
            or rfonts.get(f"{{{_W}}}cs")
        )

    # Font size (half-points → points)
    sz = rpr.find(f"{{{_W}}}sz")
    if sz is not None:
        val = sz.get(f"{{{_W}}}val")
        if val:
            font.size_pt = float(val) / _HALF_PT

    # Bold
    b = rpr.find(f"{{{_W}}}b")
    if b is not None:
        font.bold = b.get(f"{{{_W}}}val", "true") != "false"

    # Italic
    i = rpr.find(f"{{{_W}}}i")
    if i is not None:
        font.italic = i.get(f"{{{_W}}}val", "true") != "false"

    # Color
    color = rpr.find(f"{{{_W}}}color")
    if color is not None:
        val = color.get(f"{{{_W}}}val")
        if val and val.lower() != "auto":
            font.color = f"#{val}"

    # Underline
    u = rpr.find(f"{{{_W}}}u")
    if u is not None:
        font.underline = u.get(f"{{{_W}}}val", "single")

    # Strike
    strike = rpr.find(f"{{{_W}}}strike")
    if strike is not None:
        font.strike = strike.get(f"{{{_W}}}val", "true") != "false"

    # Small caps
    small_caps = rpr.find(f"{{{_W}}}smallCaps")
    if small_caps is not None:
        font.small_caps = small_caps.get(f"{{{_W}}}val", "true") != "false"

    # All caps
    caps = rpr.find(f"{{{_W}}}caps")
    if caps is not None:
        font.all_caps = caps.get(f"{{{_W}}}val", "true") != "false"

    return font


def _parse_para_props(ppr: Any) -> ParagraphFormat:
    """Extract ParagraphFormat from a w:pPr element."""
    fmt = ParagraphFormat()

    # Alignment
    jc = ppr.find(f"{{{_W}}}jc")
    if jc is not None:
        fmt.alignment = jc.get(f"{{{_W}}}val", "").upper()

    # Spacing
    spacing = ppr.find(f"{{{_W}}}spacing")
    if spacing is not None:
        before = spacing.get(f"{{{_W}}}before")
        if before:
            fmt.space_before_pt = float(before) / _TWIPS_PER_PT
        after = spacing.get(f"{{{_W}}}after")
        if after:
            fmt.space_after_pt = float(after) / _TWIPS_PER_PT
        line = spacing.get(f"{{{_W}}}line")
        if line:
            fmt.line_spacing = float(line) / 240.0  # 240 twips = single
        rule = spacing.get(f"{{{_W}}}lineRule")
        if rule:
            fmt.line_spacing_rule = rule.upper()

    # Indentation
    ind = ppr.find(f"{{{_W}}}ind")
    if ind is not None:
        left = ind.get(f"{{{_W}}}left")
        if left:
            fmt.indent_left_pt = float(left) / _TWIPS_PER_PT
        right = ind.get(f"{{{_W}}}right")
        if right:
            fmt.indent_right_pt = float(right) / _TWIPS_PER_PT
        first_line = ind.get(f"{{{_W}}}firstLine")
        if first_line:
            fmt.indent_first_line_pt = float(first_line) / _TWIPS_PER_PT
        hanging = ind.get(f"{{{_W}}}hanging")
        if hanging:
            fmt.indent_hanging_pt = float(hanging) / _TWIPS_PER_PT

    # Keep with next
    kwn = ppr.find(f"{{{_W}}}keepNext")
    if kwn is not None:
        fmt.keep_with_next = True

    # Keep together
    kt = ppr.find(f"{{{_W}}}keepLines")
    if kt is not None:
        fmt.keep_together = True

    # Page break before
    pbb = ppr.find(f"{{{_W}}}pageBreakBefore")
    if pbb is not None:
        fmt.page_break_before = True

    return fmt


def _parse_docx_numbering(xml_bytes: bytes | None) -> list[NumberingDef]:
    """Parse numbering definitions from numbering.xml."""
    if not xml_bytes:
        return []

    root = etree.fromstring(xml_bytes)
    abstract_map: dict[int, list[NumberingLevel]] = {}

    for abstract in root.findall(f"{{{_W}}}abstractNum"):
        abs_id = int(abstract.get(f"{{{_W}}}abstractNumId", "0"))
        levels: list[NumberingLevel] = []
        for lvl_el in abstract.findall(f"{{{_W}}}lvl"):
            ilvl = int(lvl_el.get(f"{{{_W}}}ilvl", "0"))
            num_fmt_el = lvl_el.find(f"{{{_W}}}numFmt")
            num_fmt = num_fmt_el.get(f"{{{_W}}}val", "bullet") if num_fmt_el is not None else "bullet"
            lvl_text_el = lvl_el.find(f"{{{_W}}}lvlText")
            lvl_text = lvl_text_el.get(f"{{{_W}}}val", "") if lvl_text_el is not None else ""
            start_el = lvl_el.find(f"{{{_W}}}start")
            start = int(start_el.get(f"{{{_W}}}val", "1")) if start_el is not None else 1

            indent_left_pt = None
            hanging_pt = None
            ind = lvl_el.find(f"{{{_W}}}pPr/{{{_W}}}ind")
            if ind is not None:
                left = ind.get(f"{{{_W}}}left")
                if left:
                    indent_left_pt = float(left) / _TWIPS_PER_PT
                hang = ind.get(f"{{{_W}}}hanging")
                if hang:
                    hanging_pt = float(hang) / _TWIPS_PER_PT

            levels.append(NumberingLevel(
                level=ilvl,
                num_format=num_fmt,
                level_text=lvl_text,
                start=start,
                indent_left_pt=indent_left_pt,
                hanging_pt=hanging_pt,
            ))
        abstract_map[abs_id] = levels

    results: list[NumberingDef] = []
    for num_el in root.findall(f"{{{_W}}}num"):
        num_id = int(num_el.get(f"{{{_W}}}numId", "0"))
        abs_ref = num_el.find(f"{{{_W}}}abstractNumId")
        abs_id = int(abs_ref.get(f"{{{_W}}}val", "0")) if abs_ref is not None else 0
        results.append(NumberingDef(
            num_id=num_id,
            abstract_num_id=abs_id,
            levels=abstract_map.get(abs_id, []),
        ))

    return results


def _parse_docx_section_props(xml_bytes: bytes | None) -> SectionProperties | None:
    """Parse the first section properties from document.xml body."""
    if not xml_bytes:
        return None

    root = etree.fromstring(xml_bytes)
    body = root.find(f"{{{_W}}}body")
    if body is None:
        return None

    sect_pr = body.find(f"{{{_W}}}sectPr")
    if sect_pr is None:
        return None

    props = SectionProperties()

    pg_sz = sect_pr.find(f"{{{_W}}}pgSz")
    if pg_sz is not None:
        w = pg_sz.get(f"{{{_W}}}w")
        h = pg_sz.get(f"{{{_W}}}h")
        if w:
            props.page_width_pt = float(w) / _TWIPS_PER_PT
        if h:
            props.page_height_pt = float(h) / _TWIPS_PER_PT
        orient = pg_sz.get(f"{{{_W}}}orient")
        if orient:
            props.orientation = orient

    pg_mar = sect_pr.find(f"{{{_W}}}pgMar")
    if pg_mar is not None:
        for attr, field_name in [
            ("top", "margin_top_pt"),
            ("bottom", "margin_bottom_pt"),
            ("left", "margin_left_pt"),
            ("right", "margin_right_pt"),
        ]:
            val = pg_mar.get(f"{{{_W}}}{attr}")
            if val:
                setattr(props, field_name, float(val) / _TWIPS_PER_PT)

    cols = sect_pr.find(f"{{{_W}}}cols")
    if cols is not None:
        num = cols.get(f"{{{_W}}}num")
        if num:
            props.columns = int(num)

    return props


# ---------------------------------------------------------------------------
# PPTX extraction
# ---------------------------------------------------------------------------

def extract_pptx_styles(pptx_path: Path) -> ExtractedStyleSheet:
    """
    Extract slide layouts, placeholder geometry, and theme from a PPTX template.
    """
    pptx_path = Path(pptx_path)

    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ImportError("python-pptx is required. Run: pip install python-pptx") from exc

    prs = Presentation(str(pptx_path))
    layouts: list[PptxSlideLayout] = []

    for idx, slide in enumerate(prs.slides):
        placeholders: list[PlaceholderInfo] = []
        for shape in slide.shapes:
            ph_type = "unknown"
            ph_idx = -1
            if shape.is_placeholder:
                ph = shape.placeholder_format
                ph_idx = ph.idx
                ph_type = _pptx_placeholder_type(ph.type)

            font_info = None
            if shape.has_text_frame and shape.text_frame.paragraphs:
                first_para = shape.text_frame.paragraphs[0]
                if first_para.runs:
                    font_info = _extract_pptx_run_font(first_para.runs[0])

            placeholders.append(PlaceholderInfo(
                idx=ph_idx if ph_idx >= 0 else idx * 100 + len(placeholders),
                type=ph_type,
                name=shape.name,
                left_emu=shape.left or 0,
                top_emu=shape.top or 0,
                width_emu=shape.width or 0,
                height_emu=shape.height or 0,
                font=font_info,
            ))

        layout_name = f"Slide {idx}"
        if slide.slide_layout:
            layout_name = slide.slide_layout.name or layout_name

        layouts.append(PptxSlideLayout(
            index=idx,
            name=layout_name,
            placeholders=placeholders,
        ))

    # Slide dimensions
    slide_width = prs.slide_width or 0
    slide_height = prs.slide_height or 0

    # Extract theme from ZIP
    theme = ThemeInfo()
    try:
        with ZipFile(pptx_path) as archive:
            for name in archive.namelist():
                if "theme" in name.lower() and name.endswith(".xml"):
                    theme = _parse_theme(archive.read(name))
                    break
    except Exception as exc:
        logger.warning("Could not extract PPTX theme: %s", exc)

    logger.info(
        "Extracted from PPTX: %d slide layouts, %dx%d EMU",
        len(layouts), slide_width, slide_height,
    )

    return ExtractedStyleSheet(
        format="pptx",
        source_file=pptx_path.name,
        extracted_at=ExtractedStyleSheet.timestamp(),
        slide_layouts=layouts,
        slide_width_emu=slide_width,
        slide_height_emu=slide_height,
        theme=theme,
    )


def _pptx_placeholder_type(ph_type: Any) -> str:
    """Convert python-pptx placeholder type enum to string label."""
    type_map = {
        0: "unknown",
        1: "body",
        2: "chart",
        3: "bitmap",
        4: "media_clip",
        5: "org_chart",
        6: "table",
        7: "slide_image",
        10: "mixed",
        12: "footer",
        13: "title",
        14: "subtitle",
        15: "center_title",
    }
    try:
        int_val = int(ph_type) if ph_type is not None else 0
        return type_map.get(int_val, f"type_{int_val}")
    except (TypeError, ValueError):
        return str(ph_type) if ph_type else "unknown"


def _extract_pptx_run_font(run: Any) -> FontProperties:
    """Extract font properties from a python-pptx Run object."""
    font = FontProperties()
    try:
        rf = run.font
        if rf.name:
            font.name = rf.name
        if rf.size:
            font.size_pt = rf.size.pt
        font.bold = rf.bold
        font.italic = rf.italic
        if rf.color and rf.color.rgb:
            font.color = f"#{rf.color.rgb}"
    except Exception:
        pass
    return font


# ---------------------------------------------------------------------------
# Theme extraction (shared between DOCX and PPTX)
# ---------------------------------------------------------------------------

def _parse_theme(xml_bytes: bytes | None) -> ThemeInfo:
    """Parse theme fonts and colors from theme1.xml."""
    theme = ThemeInfo()
    if not xml_bytes:
        return theme

    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return theme

    # Font scheme
    major = root.find(f".//{{{_A}}}majorFont/{{{_A}}}latin")
    if major is not None:
        theme.major_font = major.get("typeface")

    minor = root.find(f".//{{{_A}}}minorFont/{{{_A}}}latin")
    if minor is not None:
        theme.minor_font = minor.get("typeface")

    # Color scheme
    clr_scheme = root.find(f".//{{{_A}}}clrScheme")
    if clr_scheme is not None:
        for child in clr_scheme:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            # Colors are stored in child elements like <a:srgbClr val="..."/>
            srgb = child.find(f"{{{_A}}}srgbClr")
            if srgb is not None:
                theme.colors[tag] = f"#{srgb.get('val', '')}"
            else:
                sys_clr = child.find(f"{{{_A}}}sysClr")
                if sys_clr is not None:
                    last_clr = sys_clr.get("lastClr", "")
                    if last_clr:
                        theme.colors[tag] = f"#{last_clr}"

    return theme
