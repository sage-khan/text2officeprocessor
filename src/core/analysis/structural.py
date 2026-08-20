"""
Deterministic structural analysis for layout manifests.

This is the "structural pass" from docs/architecture.md §5: pure template
inspection, no LLM involved. Every value produced here is measurable from
the template file itself and always overrides an LLM guess when the two
disagree (see `manifest.generate_pptx_manifest`).
"""
from __future__ import annotations

from typing import Any

from src.core.analysis.models import SectionManifest, SlideManifest, SlotManifest

# Rough per-shape text-capacity estimate, reusing the same constants the
# PPTX engine's own overflow heuristic uses (`_estimate_text_overflow` in
# src/core/engines/pptx/engine.py) so a manifest's `capacity` figure is
# consistent with what will actually trigger auto-shrink at render time.
_ASSUMED_FONT_PT = 18.0
_CHAR_WIDTH_RATIO = 0.55
_LINE_HEIGHT_RATIO = 1.35
_EMU_PER_PT = 12700


def _capacity_chars(width_emu: int, height_emu: int) -> int:
    if not width_emu or not height_emu:
        return 0
    width_pt = width_emu / _EMU_PER_PT
    height_pt = height_emu / _EMU_PER_PT
    char_width_pt = _ASSUMED_FONT_PT * _CHAR_WIDTH_RATIO
    line_height_pt = _ASSUMED_FONT_PT * _LINE_HEIGHT_RATIO
    chars_per_line = max(1, width_pt / char_width_pt)
    lines_available = max(1, height_pt / line_height_pt)
    return int(chars_per_line * lines_available)


def classify_pptx_slide_structure(slide: Any) -> dict[str, Any]:
    """
    Inspect a template slide's shapes and produce structural signals an LLM
    (or human) can use to decide which content shape belongs here.

    Returns a dict with shape counts, detected groupings, and a best-guess
    `content_affinity` label (the guess is heuristic — always show the raw
    signals too so an LLM classification pass, or a human, can override it).
    """
    from src.core.engines.pptx.engine import _find_bullet_shape_group

    text_shapes = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
    picture_shapes = [s for s in slide.shapes if s.shape_type == 13]  # MSO_SHAPE_TYPE.PICTURE

    bullet_group = _find_bullet_shape_group(slide)
    bullet_group_size = len(bullet_group) if bullet_group else 0

    # Pattern-A bullets: a single shape with several mostly-empty paragraphs.
    pattern_a_bullets = 0
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        paras = shape.text_frame.paragraphs
        whitespace_count = sum(1 for p in paras if not p.text.strip())
        if len(paras) >= 3 and whitespace_count >= 3:
            pattern_a_bullets = len(paras)
            break

    # Repeated short title/body shape pairs ⇒ card-grid layouts
    # (Key Highlights, Features, Benefits, Excellence Grid).
    short_text_shapes = [s for s in text_shapes if len(s.text_frame.text.strip()) <= 80]
    card_like_count = len(short_text_shapes)

    signals: dict[str, Any] = {
        "shape_count": len(list(slide.shapes)),
        "text_shape_count": len(text_shapes),
        "picture_count": len(picture_shapes),
        "bullet_group_shapes": bullet_group_size,
        "pattern_a_bullet_paragraphs": pattern_a_bullets,
        "short_text_shapes": card_like_count,
    }

    if bullet_group_size >= 2 or pattern_a_bullets >= 3:
        guess = "bullets"
    elif picture_shapes and len(text_shapes) <= 2:
        guess = "diagram"
    elif card_like_count >= 5:
        guess = "features_or_benefits"
    elif card_like_count == 4:
        guess = "key_highlights"
    elif card_like_count == 3:
        guess = "grid"
    elif len(text_shapes) <= 2 and any(len(s.text_frame.text.strip()) < 40 for s in text_shapes):
        guess = "section_header_or_single_point"
    else:
        guess = "unknown"

    signals["guessed_content_affinity"] = guess
    return signals


_AFFINITY_BY_GUESS: dict[str, list[str]] = {
    "bullets": ["bullets"],
    "diagram": ["diagram", "image_heavy"],
    "features_or_benefits": ["feature_grid", "benefits_grid"],
    "key_highlights": ["key_highlights", "comparison"],
    "grid": ["grid", "key_highlights"],
    "section_header_or_single_point": ["section_header", "single_point", "stats"],
    "unknown": [],
}


def build_pptx_slide_manifest(
    index: int, slide: Any, slide_width_emu: int = 0, slide_height_emu: int = 0,
) -> SlideManifest:
    """Deterministic-only SlideManifest for one bank slide — no LLM input."""
    from src.core.engines.pptx.image_injector import find_image_slot

    signals = classify_pptx_slide_structure(slide)
    guess = signals["guessed_content_affinity"]

    slots: list[SlotManifest] = []

    image_slot = find_image_slot(slide)
    if image_slot is not None:
        _label_shape, _frame_shape, (left, top, width, height) = image_slot
        slots.append(SlotManifest(
            role="image_slot_1",
            kind="picture_placeholder",
            position_emu={"left": left, "top": top, "width": width, "height": height},
            accepts=["image"],
            injection_recipe="inject_template_image",
            aspect_ratio=round(width / height, 3) if height else None,
        ))

    if signals["bullet_group_shapes"] >= 2 or signals["pattern_a_bullet_paragraphs"] >= 3:
        slots.append(SlotManifest(
            role="bullets",
            kind="placeholder",
            accepts=["text"],
            injection_recipe="set_bullets",
        ))

    if signals["short_text_shapes"] >= 3 and guess in (
        "features_or_benefits", "key_highlights", "grid",
    ):
        for n in range(1, signals["short_text_shapes"] + 1):
            slots.append(SlotManifest(
                role=f"card_{n}",
                kind="textbox_pattern",
                accepts=["text"],
                injection_recipe="apply_items",
            ))

    if not slots:
        # A slide with no detected structured slot still accepts plain text
        # replacement against whatever placeholder text it carries.
        slots.append(SlotManifest(
            role="title",
            kind="placeholder",
            accepts=["text"],
            injection_recipe="single_run_replace",
        ))

    width_emu, height_emu = slide_width_emu, slide_height_emu

    capacity = {}
    if width_emu and height_emu:
        capacity["title_max_chars"] = _capacity_chars(width_emu, int(height_emu * 0.2))
        capacity["body_max_chars_per_slot"] = _capacity_chars(width_emu, int(height_emu * 0.6))
    if signals["short_text_shapes"] >= 3:
        capacity["max_items"] = signals["short_text_shapes"]

    return SlideManifest(
        index=index,
        layout_name=slide.slide_layout.name,
        content_affinity=_AFFINITY_BY_GUESS.get(guess, []),
        capacity=capacity,
        slots=slots,
        clone_strategy="slidepart_clone",
        notes=f"structural guess: {guess} ({signals['text_shape_count']} text shape(s), "
              f"{signals['picture_count']} picture(s))",
    )


def build_docx_section_manifests(doc: Any) -> list[SectionManifest]:
    """
    Deterministic structural pass over a DOCX template: one SectionManifest
    per distinct heading style actually used in the body, plus a synthetic
    "body" section describing whether the template supports tables/images
    at all. Unlike the PPTX slide bank, a DOCX template has no fixed set of
    discrete slots to enumerate — `_inject_section()` walks the template
    body in document order and injects by content-block type, so what a
    caller actually needs to know is: which heading levels exist, and can
    a table/image go here at all.
    """
    sections: list[SectionManifest] = []
    seen_styles: set[str] = set()

    for para in doc.paragraphs:
        style_name = (para.style.name if para.style else "") or ""
        if not style_name.lower().startswith("heading"):
            continue
        if style_name in seen_styles:
            continue
        seen_styles.add(style_name)
        sections.append(SectionManifest(
            role=f"heading_{style_name.lower().replace(' ', '_')}",
            heading_style=style_name,
            supports_table=False,
            has_image_anchor=False,
            notes=f"paragraph style '{style_name}'",
        ))

    sections.append(SectionManifest(
        role="body",
        heading_style=None,
        supports_table=len(doc.tables) > 0,
        has_image_anchor=len(doc.inline_shapes) > 0,
        notes=f"{len(doc.tables)} table(s), {len(doc.inline_shapes)} inline image(s) in template body",
    ))

    return sections
