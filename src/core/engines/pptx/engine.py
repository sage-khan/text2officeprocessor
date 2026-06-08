"""
PPTX Engine — SlidePart Clone + Inject method.

This engine implements the proven SlidePart cloning approach from text2officeprocessor-rules.md.
Key guarantees:
- Background images and all complex formatting are preserved via XML-level cloning
- Text replacement happens at the run level only (never text_frame.text = ...)
- Three-layer replacement strategy: single-run, cross-run, cross-paragraph
- Markdown artifacts are stripped before saving
- Template slides are removed after content slides are generated

This is the ONLY supported PPTX generation method — see rule file for why
other methods (add_slide, deepcopy, Pandoc) fail.
"""

from __future__ import annotations

import copy
import logging
import re
from pathlib import Path
from typing import Any

from lxml import etree

from src.core.exceptions import RenderError, TemplateNotFoundError
from src.core.models import SlideDefinition, SlidePlan

logger = logging.getLogger(__name__)

PPTX_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MARKDOWN_ARTIFACTS = ["***", "**", "__"]


# ---------------------------------------------------------------------------
# Slide duplication (proven SlidePart clone method)
# ---------------------------------------------------------------------------

def _get_next_slide_num(prs: Any) -> int:
    """Find the next unused slide number for partname construction."""
    nums: list[int] = []
    for slide in prs.slides:
        m = re.search(r"slide(\d+)", str(slide.part.partname))
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


def duplicate_slide(prs: Any, slide_index: int) -> Any:
    """
    Clone a template slide, preserving backgrounds, images, and all formatting.

    This is the canonical method — never use add_slide() or deepcopy(slide).

    Args:
        prs: python-pptx Presentation object.
        slide_index: Zero-based index of the template slide to clone.

    Returns:
        The newly cloned slide object (last slide in prs.slides).
    """
    from pptx.opc.package import PackURI
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.parts.slide import SlidePart

    source_slide = prs.slides[slide_index]
    source_part = source_slide.part

    # Deep copy the slide XML element — preserves all shapes, backgrounds, etc.
    new_xml = copy.deepcopy(source_part._element)

    next_num = _get_next_slide_num(prs)
    new_partname = PackURI(f"/ppt/slides/slide{next_num}.xml")

    # Construct new SlidePart: positional args only (not keyword)
    # Signature: SlidePart(partname, content_type, package, element)
    new_part = SlidePart(
        new_partname,
        source_part.content_type,
        prs.part.package,
        new_xml,
    )

    # Copy all relationships: images, slide layouts, hyperlinks, etc.
    for rel_key in source_part.rels:
        rel = source_part.rels[rel_key]
        new_part.rels.get_or_add(rel.reltype, rel._target)

    # Register the new slide part in the presentation package
    rId = prs.part.relate_to(new_part, RT.SLIDE)

    # Add a sldId entry to the presentation's sldIdLst
    sldIdLst = prs.slides._sldIdLst
    existing_ids = [
        int(e.get("id")) for e in sldIdLst if e.get("id")
    ]
    new_id = max(existing_ids) + 1 if existing_ids else 256

    new_sld_id = etree.SubElement(sldIdLst, f"{{{PPTX_NS}}}sldId")
    new_sld_id.set("id", str(new_id))
    new_sld_id.set(f"{{{REL_NS}}}id", rId)

    return prs.slides[len(prs.slides) - 1]


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize curly quotes and apostrophes to straight equivalents."""
    return (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


# ---------------------------------------------------------------------------
# Text replacement — three-layer strategy
# ---------------------------------------------------------------------------

def replace_text_everywhere(slide: Any, old_text: str, new_text: str) -> bool:
    """
    Replace all occurrences of old_text with new_text in a slide.

    Handles:
    - Single-run matches (most common)
    - Cross-run matches within the same paragraph
    - Cross-paragraph matches (e.g., "EXCELLENCE IN THE\\nMAKING")
    - Group shapes (recursively)
    - Curly quote normalization

    Args:
        slide: python-pptx Slide object.
        old_text: The placeholder text to replace (may contain newlines).
        new_text: The replacement text.

    Returns:
        True if at least one replacement was made.
    """
    replaced = False
    old_norm = _normalize(old_text)

    for shape in slide.shapes:
        if not shape.has_text_frame:
            # Handle group shapes
            if shape.shape_type == 6:
                try:
                    for child in shape.shapes:
                        if child.has_text_frame:
                            for paragraph in child.text_frame.paragraphs:
                                for run in paragraph.runs:
                                    if old_norm in _normalize(run.text):
                                        run.text = _normalize(run.text).replace(old_norm, new_text)
                                        replaced = True
                except Exception:
                    pass
            continue

        tf = shape.text_frame

        # Layer 1: per-paragraph single-run and cross-run match
        for paragraph in tf.paragraphs:
            full_text = "".join(r.text for r in paragraph.runs)
            full_norm = _normalize(full_text)

            if old_norm not in full_norm:
                continue

            single_run_match = False
            for ridx, run in enumerate(paragraph.runs):
                if old_norm in _normalize(run.text):
                    run.text = _normalize(run.text).replace(old_norm, new_text)
                    # If this run now holds the full replacement, blank trailing runs
                    # (handles "EXCELLENCE IN THE" + "MAKING" two-run pattern)
                    if _normalize(run.text.strip()) == new_text.strip():
                        for trailing_run in paragraph.runs[ridx + 1:]:
                            trailing_run.text = ""
                    replaced = True
                    single_run_match = True
                    break

            if not single_run_match:
                # Cross-run match: merge into first run
                if paragraph.runs:
                    paragraph.runs[0].text = full_norm.replace(old_norm, new_text)
                    for trailing_run in paragraph.runs[1:]:
                        trailing_run.text = ""
                    replaced = True

        if replaced:
            continue

        # Layer 2: cross-paragraph match (e.g., multiline title across paragraphs)
        para_texts = ["".join(r.text for r in p.runs) for p in tf.paragraphs]
        combined = "\n".join(para_texts)
        combined_norm = _normalize(combined)

        if old_norm in combined_norm:
            match_start = combined_norm.index(old_norm)
            char_count = 0
            first_para_idx: int | None = None
            last_para_idx: int | None = None

            for pidx, pt in enumerate(para_texts):
                para_end = char_count + len(pt)
                if first_para_idx is None and para_end > match_start:
                    first_para_idx = pidx
                if char_count < match_start + len(old_norm):
                    last_para_idx = pidx
                char_count = para_end + 1

            if first_para_idx is not None:
                first_para = tf.paragraphs[first_para_idx]
                if first_para.runs:
                    first_para.runs[0].text = new_text
                    for trailing_run in first_para.runs[1:]:
                        trailing_run.text = ""
                if last_para_idx is not None:
                    for pidx in range(first_para_idx + 1, last_para_idx + 1):
                        for r in tf.paragraphs[pidx].runs:
                            r.text = ""
                replaced = True

    return replaced


# ---------------------------------------------------------------------------
# Bullet injection
# ---------------------------------------------------------------------------

_BULLET_GLYPHS = ("•", "◦", "▪", "●", "○", "‣", "·", "-", "*", "–", "—")
_BULLET_GLYPH_RE = re.compile(
    r"^(\s*(?:" + "|".join(re.escape(g) for g in _BULLET_GLYPHS) + r")\s*)"
)
_BULLET_PLACEHOLDER_RE = re.compile(r"(?i)^\s*(bullet point|point|item)\s+\S+")


def _looks_like_bullet_placeholder(text: str) -> bool:
    """Heuristic: a short single-line shape that looks like a bullet slot."""
    stripped = text.strip()
    if not stripped or len(stripped) > 200 or "\n" in stripped:
        return False
    return bool(_BULLET_GLYPH_RE.match(stripped) or _BULLET_PLACEHOLDER_RE.match(stripped))


def _split_bullet_glyph(text: str) -> tuple[str, str]:
    """Split leading bullet glyph (with surrounding whitespace) from the rest."""
    match = _BULLET_GLYPH_RE.match(text)
    if match:
        return match.group(1), text[match.end():]
    return "", text


def _find_bullet_shape_group(slide: Any) -> list[Any] | None:
    """
    Find sibling shapes that each hold a single bullet placeholder line
    (the "one shape per bullet" template pattern). Returns the shapes
    sorted top-to-bottom, or None if no such group exists.
    """
    candidates = [
        shape
        for shape in slide.shapes
        if shape.has_text_frame and _looks_like_bullet_placeholder(shape.text_frame.text)
    ]
    if len(candidates) >= 2:
        candidates.sort(key=lambda s: s.top)
        return candidates
    return None


def _clone_sibling_shape(slide: Any, source_shape: Any) -> Any:
    """XML-level clone of a shape, inserted immediately after the source."""
    new_element = copy.deepcopy(source_shape._element)
    source_shape._element.addnext(new_element)
    for shape in slide.shapes:
        if shape._element is new_element:
            return shape
    raise RuntimeError("Failed to locate cloned shape after insertion")


def _fill_bullet_shape_group(slide: Any, group: list[Any], bullet_texts: list[str]) -> None:
    """Inject one bullet per shape, cloning/blanking shapes as needed to match counts."""
    if len(bullet_texts) > len(group):
        last_top = group[-1].top
        spacing = (group[-1].top - group[-2].top) if len(group) >= 2 else group[-1].height
        shortfall = len(bullet_texts) - len(group)
        for i in range(shortfall):
            clone = _clone_sibling_shape(slide, group[-1])
            clone.top = last_top + spacing * (i + 1)
            group.append(clone)

    for i, shape in enumerate(group):
        tf = shape.text_frame
        para = tf.paragraphs[0]
        if i < len(bullet_texts):
            glyph, _ = _split_bullet_glyph(para.text)
            new_text = f"{glyph}{bullet_texts[i]}" if glyph else bullet_texts[i]
            if para.runs:
                para.runs[0].text = new_text
                for trailing_run in para.runs[1:]:
                    trailing_run.text = ""
            else:
                para.add_run().text = new_text
        else:
            for r in para.runs:
                r.text = ""
        for extra_para in tf.paragraphs[1:]:
            for r in extra_para.runs:
                r.text = ""


def set_bullets(slide: Any, bullet_texts: list[str]) -> bool:
    """
    Inject bullet text into the slide's bullet area.

    Supports two template patterns:
      A) A single text frame with multiple mostly-empty paragraphs
         (one paragraph per bullet).
      B) A group of sibling shapes, each holding exactly one bullet
         placeholder line (e.g. separate "TextBox" shapes stacked vertically).

    Args:
        slide: python-pptx Slide object.
        bullet_texts: List of bullet strings to inject.

    Returns:
        True if bullets were successfully injected.
    """
    # Pattern A: single multi-paragraph placeholder shape.
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        tf = shape.text_frame
        paras = tf.paragraphs

        whitespace_count = sum(1 for p in paras if not p.text.strip())
        if len(paras) >= 3 and whitespace_count >= 3:
            for i in range(min(len(bullet_texts), len(paras))):
                if paras[i].runs:
                    paras[i].runs[0].text = bullet_texts[i]
                    for trailing_run in paras[i].runs[1:]:
                        trailing_run.text = ""
                else:
                    # Add a run if there are none
                    paras[i].add_run().text = bullet_texts[i]
            # Clear any remaining unfilled paragraphs
            for i in range(len(bullet_texts), len(paras)):
                for r in paras[i].runs:
                    r.text = ""
            return True

    # Pattern B: one sibling shape per bullet.
    group = _find_bullet_shape_group(slide)
    if group:
        _fill_bullet_shape_group(slide, group, bullet_texts)
        return True

    return False


# ---------------------------------------------------------------------------
# Structured item injection (Key Highlights, Features, Benefits, Grid)
# ---------------------------------------------------------------------------

def apply_items(slide: Any, template_index: int, items: dict[str, str]) -> None:
    """
    Apply structured card/item content to complex slide types.

    Supported template indices:
    - 7: Key Highlights — 4 columns (card_N_title, card_N_body)
    - 9: Features 6-pill (item_N_title, item_N_body)
    - 10: Benefits 6-item (item_N_title, item_N_body)
    - 11: Excellence Grid — 3 items in Rectangle shapes (item_0N_title, item_0N_body)

    Args:
        slide: python-pptx Slide object.
        template_index: The template_index of the cloned slide.
        items: Dict of item keys to text values.
    """
    if template_index == 7:
        card_idx = 0
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            if "Key Element Title" in shape.text_frame.text:
                card_idx += 1
                _replace_card(shape, f"card_{card_idx}_title", f"card_{card_idx}_body", items, "Key Element Title")

    elif template_index in {9, 10}:
        item_idx = 0
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            if "Key Element Title Here" in shape.text_frame.text:
                item_idx += 1
                _replace_card(shape, f"item_{item_idx}_title", f"item_{item_idx}_body", items, "Key Element Title Here")

    elif template_index == 11:
        rect_idx = 0
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            if "Rectangle" not in shape.name:
                continue
            if "Key Element Title Here" in shape.text_frame.text:
                rect_idx += 1
                _replace_card(shape, f"item_0{rect_idx}_title", f"item_0{rect_idx}_body", items, "Key Element Title Here")


def _replace_card(
    shape: Any,
    title_key: str,
    body_key: str,
    items: dict[str, str],
    title_marker: str,
) -> None:
    """Replace title and body runs within a card/item shape."""
    if title_key not in items:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if title_marker in run.text:
                run.text = items.get(title_key, run.text)
            elif any(
                kw in run.text.lower()
                for kw in ["sample text", "simply add", "description here", "this text is editable"]
            ):
                run.text = items.get(body_key, run.text)


# ---------------------------------------------------------------------------
# Template slide removal
# ---------------------------------------------------------------------------

def remove_original_slides(prs: Any, count: int) -> None:
    """
    Remove the first `count` slides from the presentation.

    Called after all content slides have been cloned to strip the
    template bank slides from the final output.

    Args:
        prs: python-pptx Presentation object.
        count: Number of leading template slides to remove.
    """
    sldIdLst = prs.slides._sldIdLst
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

    to_remove = list(sldIdLst)[:count]
    for sldId in to_remove:
        rId = sldId.get(f"{r_ns}id")
        sldIdLst.remove(sldId)
        if rId:
            try:
                prs.part.drop_rel(rId)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Artifact sanitization
# ---------------------------------------------------------------------------

def sanitize_presentation(prs: Any) -> None:
    """
    Strip markdown formatting artifacts from all text runs in the presentation.

    Removes: ***, **, __
    """
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        for artifact in MARKDOWN_ARTIFACTS:
                            run.text = run.text.replace(artifact, "")


# ---------------------------------------------------------------------------
# Text overflow — auto font-size reduction
# ---------------------------------------------------------------------------

# Minimum font size (pt) we will ever shrink to. Below this the text becomes
# unreadable, so we stop and log a warning instead.
MIN_FONT_SIZE_PT = 8

# The heuristic: estimate how many characters fit in a text frame by comparing
# total character count against an allowed capacity derived from the shape's
# bounding box area and the current average font size.
# We use EMU units (914400 EMU = 1 inch). A typical slide is 9144000 x 5143500 EMU.
EMU_PER_PT = 12700  # 1 pt = 12700 EMU


def _get_run_font_size_pt(run: Any) -> float | None:
    """Return the explicit font size of a run in points, or None if inherited."""
    if run.font and run.font.size:
        return run.font.size / EMU_PER_PT
    return None


def _set_run_font_size_pt(run: Any, size_pt: float) -> None:
    """Set the font size of a run in points."""
    from pptx.util import Pt
    run.font.size = Pt(size_pt)


def _collect_shape_runs(shape: Any) -> list[Any]:
    """Return all runs in a shape's text frame."""
    runs: list[Any] = []
    if not shape.has_text_frame:
        return runs
    for para in shape.text_frame.paragraphs:
        runs.extend(para.runs)
    return runs


def _estimate_text_overflow(shape: Any) -> bool:
    """
    Estimate whether a text frame's content overflows its bounding box.

    Strategy:
    - Count total characters in the text frame
    - Estimate the average font size in pt (fall back to 18pt if unset)
    - Compute approximate character capacity based on shape width and height
    - Return True if estimated character count exceeds capacity

    This is intentionally conservative — it errs toward shrinking rather
    than leaving overflowing text.
    """
    if not shape.has_text_frame:
        return False

    tf = shape.text_frame
    all_text = "".join(
        run.text for para in tf.paragraphs for run in para.runs
    )
    if not all_text.strip():
        return False

    # Collect explicit font sizes; default to 18pt if none set
    sizes = [
        _get_run_font_size_pt(run)
        for para in tf.paragraphs
        for run in para.runs
        if _get_run_font_size_pt(run) is not None
    ]
    avg_size_pt = sum(sizes) / len(sizes) if sizes else 18.0

    # Shape dimensions in pt (1 pt = 12700 EMU)
    try:
        width_pt = shape.width / EMU_PER_PT
        height_pt = shape.height / EMU_PER_PT
    except Exception:
        return False

    if width_pt <= 0 or height_pt <= 0:
        return False

    # Approximate chars per line and lines available
    char_width_pt = avg_size_pt * 0.55   # average character width ratio
    line_height_pt = avg_size_pt * 1.35  # line height including spacing
    chars_per_line = max(1, width_pt / char_width_pt)
    lines_available = max(1, height_pt / line_height_pt)
    capacity = int(chars_per_line * lines_available)

    return len(all_text) > capacity


def fit_text_to_shape(slide: Any) -> None:
    """
    Scan every text-bearing shape on a slide. For any shape whose content
    is estimated to overflow its bounding box, reduce all run font sizes
    incrementally (2pt steps) until the content fits or MIN_FONT_SIZE_PT
    is reached.

    Rules:
    - Only shapes with explicit font sizes OR where the text is clearly
      overflowing are touched.
    - Font sizes are never increased — only reduced.
    - Shapes with auto_size already enabled in the template are skipped
      (the template handles them natively).
    - Group shapes are processed recursively.

    Args:
        slide: python-pptx Slide object.
    """
    for shape in slide.shapes:
        # Recurse into group shapes
        if shape.shape_type == 6:
            try:
                for child in shape.shapes:
                    fit_text_to_shape_single(child)
            except Exception:
                pass
            continue
        fit_text_to_shape_single(shape)


def fit_text_to_shape_single(shape: Any) -> None:
    """Apply overflow shrinking to a single shape."""
    from pptx.util import Pt

    if not shape.has_text_frame:
        return

    tf = shape.text_frame

    # Skip if the template already uses auto-size on this text frame
    try:
        from pptx.enum.text import MSO_AUTO_SIZE
        if tf.auto_size in (MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE, MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT):
            return
    except Exception:
        pass

    # Iteratively reduce font size until content fits or floor is hit
    iterations = 0
    max_iterations = 20
    while _estimate_text_overflow(shape) and iterations < max_iterations:
        runs = _collect_shape_runs(shape)
        if not runs:
            break

        # Find the current minimum explicit size; fall back to 18pt
        current_sizes = [_get_run_font_size_pt(r) for r in runs if _get_run_font_size_pt(r)]
        current_min = min(current_sizes) if current_sizes else 18.0

        if current_min <= MIN_FONT_SIZE_PT:
            logger.warning(
                "Shape '%s': text still overflows at minimum font size %dpt — "
                "consider shortening the content.",
                shape.name,
                MIN_FONT_SIZE_PT,
            )
            break

        new_size = max(MIN_FONT_SIZE_PT, current_min - 2.0)

        for run in runs:
            existing = _get_run_font_size_pt(run)
            # Only reduce runs that have an explicit size set, OR reduce all
            # if no run has an explicit size (all inherited — set explicitly now)
            if existing is not None:
                _set_run_font_size_pt(run, max(MIN_FONT_SIZE_PT, existing - 2.0))
            else:
                _set_run_font_size_pt(run, new_size)

        iterations += 1

    if iterations > 0:
        logger.debug(
            "Shape '%s': font size reduced %d time(s) to fit content.",
            shape.name,
            iterations,
        )


# ---------------------------------------------------------------------------
# Main PPTX Engine class
# ---------------------------------------------------------------------------

class PPTXEngine:
    """
    Renders a SlidePlan into a PPTX file using the SlidePart clone method.

    Supports content overflow handling via PPTXContentFitter:
    - summarize: LLM condenses dense content
    - split: Distribute across multiple slides
    - shrink: Reduce font size (fallback)
    - auto: LLM selects strategy

    Usage:
        engine = PPTXEngine()  # Default: auto overflow handling if LLM available
        engine.render(slide_plan, template_path, output_path)

        engine = PPTXEngine(overflow_strategy="split")  # Force split strategy
        engine.render(slide_plan, template_path, output_path)
    """

    def __init__(
        self,
        overflow_strategy: str | None = None,
        llm_provider: Any | None = None,
    ) -> None:
        """
        Args:
            overflow_strategy: "summarize" | "split" | "shrink" | "auto" | None
                              None = load from config (default: auto)
            llm_provider: LLMProvider for summarize/auto strategies
        """
        self._overflow_strategy = overflow_strategy
        self._llm_provider = llm_provider

    def _fit_plan(self, plan: SlidePlan) -> SlidePlan:
        """Apply content fitting if enabled and provider available."""
        if self._llm_provider is None and self._overflow_strategy != "split":
            # No LLM, and split doesn't need it
            return plan

        try:
            from src.core.engines.pptx.content_fitter import (
                PPTXContentFitter,
                OverflowConfig,
                load_fitter_config,
            )
            # Load config (resolved via config_loader: repo-local, then bundled)
            config = load_fitter_config()

            # Override strategy if explicitly set
            if self._overflow_strategy:
                config.strategy = self._overflow_strategy

            fitter = PPTXContentFitter(
                provider=self._llm_provider,
                config=config,
            )

            fitted_plan = fitter.fit_slide_plan(plan)

            if len(fitted_plan.slides) != len(plan.slides):
                logger.info(
                    "Content fitting: %d slides → %d slides (%s strategy)",
                    len(plan.slides),
                    len(fitted_plan.slides),
                    config.strategy,
                )

            return fitted_plan

        except Exception as exc:
            logger.warning("Content fitting failed (%s), using original plan", exc)
            return plan

    def render(
        self,
        plan: SlidePlan,
        template_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Generate a PPTX file from a SlidePlan.

        Args:
            plan: The SlidePlan with all slide definitions.
            template_path: Path to the source .pptx template file.
            output_path: Where to write the output .pptx.

        Returns:
            The output_path on success.

        Raises:
            TemplateNotFoundError: If the template file does not exist.
            RenderError: If rendering fails for any reason.
        """
        template_path = Path(template_path)
        output_path = Path(output_path)

        if not template_path.exists():
            raise TemplateNotFoundError(f"Template not found: {template_path}")

        try:
            from pptx import Presentation
        except ImportError as exc:
            raise RenderError("python-pptx is not installed. Run: pip install python-pptx") from exc

        logger.info("Loading template: %s", template_path.name)
        try:
            prs = Presentation(str(template_path))
        except Exception as exc:
            raise TemplateNotFoundError(f"Cannot open template '{template_path}': {exc}") from exc

        bank_count = len(prs.slides)
        logger.info("Template has %d slide(s) in bank", bank_count)

        if not plan.slides:
            raise RenderError("SlidePlan contains no slides to render.")

        # Apply content fitting if configured
        fitted_plan = self._fit_plan(plan)

        # Clone and populate slides
        for sdef in fitted_plan.slides:
            self._render_slide(prs, sdef, bank_count)

        # Remove template bank slides
        logger.info("Removing %d template bank slide(s)", bank_count)
        remove_original_slides(prs, bank_count)

        # Strip markdown artifacts
        sanitize_presentation(prs)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Saving output: %s", output_path.name)
        try:
            prs.save(str(output_path))
        except Exception as exc:
            raise RenderError(f"Failed to save PPTX: {exc}") from exc

        # Quick verification
        try:
            from pptx import Presentation as _P
            check = _P(str(output_path))
            logger.info("Verified: %d slide(s) in output", len(check.slides))
        except Exception as exc:
            logger.warning("Output verification failed: %s", exc)

        return output_path

    def _render_slide(self, prs: Any, sdef: SlideDefinition, bank_count: int) -> None:
        """Clone a template slide and inject content from a SlideDefinition."""
        if sdef.template_index >= bank_count:
            logger.warning(
                "Slide %d: template_index %d is out of range (bank has %d slides). "
                "Using index 0.",
                sdef.slide_number,
                sdef.template_index,
                bank_count,
            )
            effective_index = 0
        else:
            effective_index = sdef.template_index

        logger.debug(
            "Slide %d/%d: cloning template[%d] (%s)",
            sdef.slide_number,
            sdef.template_index,
            effective_index,
            sdef.slide_type,
        )
        new_slide = duplicate_slide(prs, effective_index)

        # Apply text replacements
        for old_text, new_text in sdef.replacements.items():
            ok = replace_text_everywhere(new_slide, old_text, new_text)
            if not ok:
                logger.warning(
                    "Slide %d: replacement not found — '%s'",
                    sdef.slide_number,
                    old_text[:60],
                )

        # Apply bullet content
        if sdef.bullets:
            ok = set_bullets(new_slide, sdef.bullets)
            if not ok:
                logger.warning(
                    "Slide %d: could not find bullet area (%d bullets)",
                    sdef.slide_number,
                    len(sdef.bullets),
                )

        # Apply structured items (cards, grid, etc.)
        if sdef.items:
            # First pass: direct text replacement for templates that use literal
            # placeholder keys (e.g. "card_1_title", "card_1_body") in TextBoxes.
            for item_key, item_val in sdef.items.items():
                replace_text_everywhere(new_slide, item_key, item_val)
            # Second pass: keyword-sentinel replacement for premium templates
            # that use "Key Element Title" / "Key Element Title Here" markers.
            apply_items(new_slide, sdef.template_index, sdef.items)

        # Embed diagram image (draw.io export or direct PNG/SVG)
        if sdef.diagram_path:
            self._embed_diagram(new_slide, sdef)

        # Inject a photo/illustration into the template's own image slot,
        # cropped to preserve the slot's aspect ratio and the slide's aesthetics
        if sdef.image_path:
            self._inject_image(new_slide, sdef)

        # Auto-shrink any shape whose content exceeds its bounding box
        fit_text_to_shape(new_slide)

    def _embed_diagram(self, slide: Any, sdef: "SlideDefinition") -> None:
        """
        Export a draw.io file to PNG (or use a PNG directly) and embed it on the slide.

        The image is centred horizontally with a small margin.  If the diagram_path
        is relative it is resolved relative to the current working directory so the
        slides markdown can use paths relative to where the user runs the tool.
        """
        from pptx.util import Inches, Emu
        import tempfile

        diagram_path = Path(sdef.diagram_path)
        if not diagram_path.is_absolute():
            diagram_path = Path.cwd() / diagram_path

        if not diagram_path.exists():
            logger.warning(
                "Slide %d: diagram file not found — %s (skipping)",
                sdef.slide_number,
                diagram_path,
            )
            return

        suffix = diagram_path.suffix.lower()

        # Retrieve presentation dimensions via the slide's part relationship
        try:
            slide_w = slide.shapes._spTree.getparent().getparent().slide_width
            slide_h = slide.shapes._spTree.getparent().getparent().slide_height
        except Exception:
            from pptx.util import Inches
            slide_w = Inches(13.33)
            slide_h = Inches(7.5)

        # Resolve to a raster PNG suitable for embedding
        if suffix == ".drawio":
            try:
                from src.core.drawio.converter import export_drawio_to_png
                with tempfile.TemporaryDirectory() as tmp:
                    png_path = export_drawio_to_png(
                        diagram_path,
                        output_path=Path(tmp) / (diagram_path.stem + ".png"),
                    )
                    self._insert_image_centred(slide, png_path, slide_w, slide_h)
            except Exception as exc:
                logger.warning(
                    "Slide %d: draw.io export failed — %s (skipping diagram)",
                    sdef.slide_number,
                    exc,
                )
        elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}:
            self._insert_image_centred(slide, diagram_path, slide_w, slide_h)
        else:
            logger.warning(
                "Slide %d: unsupported diagram format '%s' — use .drawio or .png",
                sdef.slide_number,
                suffix,
            )

    def _inject_image(self, slide: Any, sdef: "SlideDefinition") -> None:
        """
        Fill the template's own image slot (placeholder shape or labelled
        rectangle, e.g. "[Image placeholder]") with the user's photo, cropped
        to the slot's aspect ratio so the template's layout is preserved.

        Falls back to a centred embed if the template has no image slot —
        this keeps `- image:` usable even on slides without a dedicated slot.
        """
        from src.core.engines.pptx.image_injector import inject_template_image

        image_path = Path(sdef.image_path)
        if not image_path.is_absolute():
            image_path = Path.cwd() / image_path

        if not image_path.exists():
            logger.warning(
                "Slide %d: image file not found — %s (skipping)",
                sdef.slide_number,
                image_path,
            )
            return

        if inject_template_image(slide, image_path, sdef.slide_number):
            return

        logger.info(
            "Slide %d: no template image slot found, falling back to centred embed",
            sdef.slide_number,
        )
        try:
            slide_w = slide.shapes._spTree.getparent().getparent().slide_width
            slide_h = slide.shapes._spTree.getparent().getparent().slide_height
        except Exception:
            from pptx.util import Inches
            slide_w = Inches(13.33)
            slide_h = Inches(7.5)
        self._insert_image_centred(slide, image_path, slide_w, slide_h)

    @staticmethod
    def _insert_image_centred(slide: Any, image_path: Path, slide_w: int, slide_h: int) -> None:
        """Add an image to the slide, centred with a standard margin."""
        from pptx.util import Inches

        MARGIN = Inches(0.5)
        max_w = slide_w - MARGIN * 2
        max_h = slide_h - MARGIN * 2

        # Add picture at full max width; python-pptx preserves aspect ratio
        pic = slide.shapes.add_picture(
            str(image_path),
            left=MARGIN,
            top=MARGIN,
            width=max_w,
        )

        # Re-centre vertically after aspect ratio is applied
        if pic.height < max_h:
            pic.top = (slide_h - pic.height) // 2
        else:
            pic.height = max_h
            pic.top = MARGIN
            pic.left = (slide_w - pic.width) // 2

