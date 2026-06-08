"""
Template-aware image injection for PPTX slides.

Unlike `_embed_diagram` (which centres a diagram PNG on an otherwise-empty
slide), this module locates the *image slot* a template already designed —
either a native picture placeholder or a labelled placeholder shape such as
`[Image placeholder]` sitting inside a frame rectangle — and fills it with
the user's photo, cropped to match the slot's aspect ratio so the template's
layout and proportions are preserved exactly.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Matches shape text that IS (not merely contains) an image-placeholder label,
# e.g. "[Image placeholder]", "Photo here", "(Insert picture)". Anchored so
# slide titles like "Image Left Slide" don't false-positive.
_IMAGE_PLACEHOLDER_RE = re.compile(
    r"(?i)^\s*[\[\(]?\s*(image|photo|picture|graphic)"
    r"(\s+(placeholder|here|goes here|insert))?\s*[\]\)]?\s*$"
)


def _native_picture_placeholder(slide: Any) -> Any | None:
    """Return a slide placeholder shape of type PICTURE, if the layout has one."""
    try:
        from pptx.enum.shapes import PP_PLACEHOLDER
    except ImportError:
        return None

    for shape in slide.placeholders:
        fmt = getattr(shape, "placeholder_format", None)
        if fmt is not None and fmt.type == PP_PLACEHOLDER.PICTURE:
            return shape
    return None


def _bbox(shape: Any) -> tuple[int, int, int, int] | None:
    try:
        return (int(shape.left), int(shape.top), int(shape.width), int(shape.height))
    except Exception:
        return None


def _overlap_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(ax, bx)
    iy = max(ay, by)
    iw = min(ax + aw, bx + bw) - ix
    ih = min(ay + ah, by + bh) - iy
    return max(0, iw) * max(0, ih)


def find_image_slot(slide: Any) -> tuple[Any, Any, tuple[int, int, int, int]] | None:
    """
    Locate the slide's image slot.

    Returns (label_shape_to_remove, frame_shape_for_bbox, bbox) where bbox is
    (left, top, width, height) in EMU, or None if no slot is found.

    Two patterns are recognised:
      1. A native picture placeholder inherited from the slide layout.
      2. A short text shape whose text reads like an image placeholder label
         (e.g. "[Image placeholder]"), optionally sitting inside a larger
         frame shape (rectangle/autoshape) that defines the visual bounds.
    """
    native = _native_picture_placeholder(slide)
    if native is not None:
        bbox = _bbox(native)
        if bbox:
            return native, native, bbox

    label_shape = None
    for shape in slide.shapes:
        if shape.has_text_frame and _IMAGE_PLACEHOLDER_RE.match(shape.text_frame.text):
            label_shape = shape
            break

    if label_shape is None:
        return None

    label_bbox = _bbox(label_shape)
    if label_bbox is None:
        return None

    label_area = label_bbox[2] * label_bbox[3]
    frame_shape = label_shape
    frame_bbox = label_bbox
    best_area = None

    # Pick the SMALLEST sibling shape that (almost) fully contains the label.
    # Overlap alone saturates once a shape contains the label — a full-slide
    # background rectangle would "win" over the actual frame by that measure,
    # so the tightest-fitting container is the right tie-breaker.
    for shape in slide.shapes:
        if shape._element is label_shape._element:
            continue
        candidate_bbox = _bbox(shape)
        if candidate_bbox is None:
            continue
        candidate_area = candidate_bbox[2] * candidate_bbox[3]
        if candidate_area < label_area:
            continue
        overlap = _overlap_area(label_bbox, candidate_bbox)
        if overlap < 0.9 * label_area:
            continue
        if best_area is None or candidate_area < best_area:
            best_area = candidate_area
            frame_shape = shape
            frame_bbox = candidate_bbox

    return label_shape, frame_shape, frame_bbox


def _crop_to_aspect(image_path: Path, target_w: int, target_h: int):
    """Centre-crop a Pillow image so its aspect ratio matches the target slot (cover-fit)."""
    from PIL import Image, ImageOps

    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = max(1, round(src_h * target_ratio))
        offset = (src_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, src_h))
    elif src_ratio < target_ratio:
        new_h = max(1, round(src_w / target_ratio))
        offset = (src_h - new_h) // 2
        img = img.crop((0, offset, src_w, offset + new_h))

    return img


def inject_template_image(slide: Any, image_path: Path, slide_number: int = 0) -> bool:
    """
    Fill the slide's template-defined image slot with `image_path`, cropped
    (cover-fit) to the slot's aspect ratio so the template's proportions and
    layout are preserved.

    Returns True if an image slot was found and filled.
    """
    if not image_path.exists():
        logger.warning("Slide %d: image file not found — %s (skipping)", slide_number, image_path)
        return False

    slot = find_image_slot(slide)
    if slot is None:
        logger.info(
            "Slide %d: no image placeholder found for '%s' — skipping template-aware injection",
            slide_number,
            image_path.name,
        )
        return False

    label_shape, frame_shape, (left, top, width, height) = slot

    try:
        cropped = _crop_to_aspect(image_path, width, height)
    except Exception as exc:
        logger.warning("Slide %d: failed to process image '%s' — %s", slide_number, image_path, exc)
        return False

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        cropped.save(tmp_path, "PNG")
        slide.shapes.add_picture(tmp_path, left=left, top=top, width=width, height=height)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Remove the label shape so its placeholder text doesn't overlay the photo.
    # The frame (if distinct) is left in place — the picture renders on top of
    # it, preserving any decorative border the template drew around the slot.
    if label_shape._element is not frame_shape._element:
        label_element = label_shape._element
        label_element.getparent().remove(label_element)
    elif label_shape.has_text_frame:
        for para in label_shape.text_frame.paragraphs:
            for run in para.runs:
                run.text = ""

    logger.info("Slide %d: injected image '%s' into template slot", slide_number, image_path.name)
    return True
