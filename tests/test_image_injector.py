"""
Tests for template-aware image injection — locating image slots in a slide
and filling them with a cropped photo while preserving template proportions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

pytest.importorskip("PIL")

from pptx import Presentation
from pptx.util import Emu

from src.core.engines.pptx.image_injector import (
    _IMAGE_PLACEHOLDER_RE,
    _crop_to_aspect,
    find_image_slot,
    inject_template_image,
)


def blank_slide():
    prs = Presentation()
    return prs, prs.slides.add_slide(prs.slide_layouts[6])


def add_textbox(slide, text, left=100, top=100, width=1000, height=500):
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    box.text_frame.text = text
    return box


def make_image(tmp_path, name="photo.jpg", size=(800, 600), color=(200, 50, 50)):
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", size, color).save(path)
    return path


# ---------------------------------------------------------------------------
# _IMAGE_PLACEHOLDER_RE — label detection (mechanical, no LLM)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "[Image placeholder]",
    "Photo here",
    "(Insert picture)",
    "image",
    "Picture",
    "Graphic goes here",
    "Insert Picture",
    "Add photo",
    "Click to add image",
    "Click here to insert picture",
])
def test_placeholder_regex_matches_known_labels(text):
    assert _IMAGE_PLACEHOLDER_RE.match(text)


@pytest.mark.parametrize("text", [
    "Image Left Slide",
    "Our Photography Team",
    "Picture-perfect quarter",
    "Quarterly Revenue Highlights",
    "",
])
def test_placeholder_regex_does_not_false_positive(text):
    assert not _IMAGE_PLACEHOLDER_RE.match(text)


# ---------------------------------------------------------------------------
# find_image_slot — label-shape pattern (with and without a frame)
# ---------------------------------------------------------------------------

def test_find_image_slot_returns_none_when_no_placeholder_present():
    _, slide = blank_slide()
    add_textbox(slide, "Quarterly Revenue Highlights")

    assert find_image_slot(slide) is None


def test_find_image_slot_locates_bare_label_shape():
    _, slide = blank_slide()
    label = add_textbox(slide, "[Image placeholder]", left=200, top=300, width=2000, height=1500)

    slot = find_image_slot(slide)

    assert slot is not None
    label_shape, frame_shape, bbox = slot
    assert label_shape._element is label._element
    assert frame_shape._element is label._element
    assert bbox == (200, 300, 2000, 1500)


def test_find_image_slot_prefers_tightest_containing_frame():
    prs, slide = blank_slide()
    # A full-slide background rectangle...
    background = slide.shapes.add_shape(1, Emu(0), Emu(0), prs.slide_width, prs.slide_height)
    # ...and a tighter frame that actually bounds the label.
    frame = slide.shapes.add_shape(1, Emu(150), Emu(150), Emu(3000), Emu(2000))
    label = add_textbox(slide, "[Image placeholder]", left=200, top=200, width=2800, height=1800)

    slot = find_image_slot(slide)

    assert slot is not None
    label_shape, frame_shape, bbox = slot
    assert label_shape._element is label._element
    assert frame_shape._element is frame._element
    assert frame_shape._element is not background._element
    assert bbox == (150, 150, 3000, 2000)


def test_find_image_slot_ignores_frames_that_dont_contain_label():
    _, slide = blank_slide()
    # Sibling shape elsewhere on the slide — should not be picked as the frame.
    slide.shapes.add_shape(1, Emu(5_000_000), Emu(5_000_000), Emu(1000), Emu(1000))
    label = add_textbox(slide, "[Image placeholder]", left=200, top=200, width=1000, height=800)

    slot = find_image_slot(slide)

    assert slot is not None
    label_shape, frame_shape, _ = slot
    assert frame_shape._element is label_shape._element is label._element


# ---------------------------------------------------------------------------
# _crop_to_aspect — cover-fit centre cropping
# ---------------------------------------------------------------------------

def test_crop_to_aspect_crops_wide_image_to_narrower_target(tmp_path):
    image_path = make_image(tmp_path, size=(1600, 800))  # 2:1

    cropped = _crop_to_aspect(image_path, target_w=1000, target_h=1000)  # 1:1

    assert cropped.size == (800, 800)


def test_crop_to_aspect_crops_tall_image_to_wider_target(tmp_path):
    image_path = make_image(tmp_path, size=(800, 1600))  # 1:2

    cropped = _crop_to_aspect(image_path, target_w=1000, target_h=500)  # 2:1

    assert cropped.size == (800, 400)


def test_crop_to_aspect_leaves_matching_ratio_untouched(tmp_path):
    image_path = make_image(tmp_path, size=(1000, 500))  # 2:1

    cropped = _crop_to_aspect(image_path, target_w=400, target_h=200)  # 2:1

    assert cropped.size == (1000, 500)


# ---------------------------------------------------------------------------
# inject_template_image — end-to-end slot fill (no LLM involved)
# ---------------------------------------------------------------------------

def test_inject_template_image_fills_label_slot_and_removes_label(tmp_path):
    _, slide = blank_slide()
    add_textbox(slide, "[Image placeholder]", left=914_400, top=914_400, width=2_743_200, height=1_828_800)
    image_path = make_image(tmp_path, size=(1200, 800))

    filled = inject_template_image(slide, image_path, slide_number=1)

    assert filled is True
    pictures = [s for s in slide.shapes if s.shape_type == 13]
    assert len(pictures) == 1
    # Label IS the frame here, so its text is cleared in place (not removed)
    # to avoid leaving a dangling empty shape where the frame border lived.
    assert not any(
        s.has_text_frame and "[image placeholder]" in s.text_frame.text.lower()
        for s in slide.shapes
    )


def test_inject_template_image_returns_false_when_no_slot():
    _, slide = blank_slide()
    add_textbox(slide, "Just a regular title")
    image_path = Path(__file__)  # any existing file path; slot lookup happens first... actually image must exist

    # Use a real image so the "no slot" branch (not the "missing file" branch) is exercised.
    import tempfile
    from PIL import Image
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        Image.new("RGB", (100, 100)).save(tmp.name)
        result = inject_template_image(slide, Path(tmp.name), slide_number=2)

    assert result is False
    assert not any(s.shape_type == 13 for s in slide.shapes)


def test_inject_template_image_returns_false_when_file_missing(tmp_path):
    _, slide = blank_slide()
    add_textbox(slide, "[Image placeholder]")

    result = inject_template_image(slide, tmp_path / "missing.jpg", slide_number=3)

    assert result is False
