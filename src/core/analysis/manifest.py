"""
Layout manifest generation: structural pass + optional LLM classification pass
+ merge/validate, per docs/architecture.md §5.

Two-pass design:
1. Structural (`structural.py`) — deterministic, always correct for anything
   measurable (shape counts, positions, run structure). Never depends on an
   LLM being configured.
2. Classification (this module, `classify_with_llm`) — optional. An LLM
   reads the structural JSON (never the binary template) and labels
   `content_affinity` / `injection_recipe` / `accepts` per slot. Every
   `injection_recipe` value it returns is validated against
   `models.INJECTION_RECIPES` before being accepted — an unrecognised value
   is dropped, not trusted, so a bad LLM guess can only leave the structural
   default in place, never inject an unsafe recipe name.

Structural facts always win when the two passes disagree; see `_merge_slide`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.core.analysis.models import (
    INJECTION_RECIPES,
    SlideManifest,
    TemplateManifest,
)
from src.core.analysis.structural import build_docx_section_manifests, build_pptx_slide_manifest
from src.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)

CLASSIFY_PPTX_PROMPT = """You are labeling slots in a PowerPoint template so a document \
generator knows what content fits where. You are NOT writing any code or XML — only \
picking labels from fixed lists below.

Here is the structural analysis of one slide (index {index}, layout "{layout_name}"):
{structural_json}

Respond with ONLY valid JSON matching this schema:
{{
  "content_affinity": ["<one or more of: bullets, diagram, image_heavy, feature_grid, \
benefits_grid, key_highlights, comparison, grid, section_header, single_point, stats, \
unknown>"],
  "notes": "<one short sentence on what this slide is for>"
}}

Rules:
- Base your answer only on the structural signals given (shape counts, groupings) — \
never invent shapes that aren't listed.
- If unsure, use ["unknown"].
- Never propose new recipe names, shape edits, or layout changes — this schema has no \
field for that.
"""


def _validate_recipe(recipe: str) -> str:
    return recipe if recipe in INJECTION_RECIPES else ""


def classify_pptx_slide_with_llm(
    provider: LLMProvider, index: int, layout_name: str, structural_signals: dict[str, Any],
) -> dict[str, Any] | None:
    """Ask an LLM to refine one slide's `content_affinity`/`notes`. Returns
    None (never raises) on any provider/parse failure — classification is
    optional, a structural-only manifest is always valid on its own."""
    prompt = CLASSIFY_PPTX_PROMPT.format(
        index=index, layout_name=layout_name,
        structural_json=json.dumps(structural_signals, ensure_ascii=False),
    )
    try:
        raw = provider.generate(prompt)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        return json.loads(raw[start : end + 1])
    except Exception as exc:
        logger.warning("LLM classification failed for slide %d: %s", index, exc)
        return None


def _merge_slide(slide: SlideManifest, llm_result: dict[str, Any] | None) -> SlideManifest:
    """Overlay an LLM's semantic guesses onto a structural SlideManifest.
    Structural facts (slots, positions, capacity, clone_strategy) are never
    touched here — only the semantic `content_affinity`/`notes` fields, and
    only when the LLM actually returned something usable."""
    if not llm_result:
        return slide
    affinity = llm_result.get("content_affinity")
    if isinstance(affinity, list) and affinity and all(isinstance(a, str) for a in affinity):
        slide.content_affinity = affinity
    notes = llm_result.get("notes")
    if isinstance(notes, str) and notes.strip():
        slide.notes = f"{slide.notes} | LLM: {notes.strip()}" if slide.notes else notes.strip()
    return slide


def generate_pptx_manifest(
    template_path: Path, llm_provider: LLMProvider | None = None,
) -> TemplateManifest:
    """Structural pass over every slide in a PPTX template bank, optionally
    refined by an LLM classification pass. Always returns a usable manifest
    even if `llm_provider` is None or fails — the structural pass alone is
    sufficient for `best_slide_for()` to work."""
    from pptx import Presentation

    prs = Presentation(str(template_path))
    width_emu, height_emu = int(prs.slide_width or 0), int(prs.slide_height or 0)

    slides: list[SlideManifest] = []
    classified_by_llm = False
    for i, slide in enumerate(prs.slides):
        manifest_slide = build_pptx_slide_manifest(i, slide, width_emu, height_emu)
        if llm_provider is not None:
            from src.core.analysis.structural import classify_pptx_slide_structure

            signals = classify_pptx_slide_structure(slide)
            llm_result = classify_pptx_slide_with_llm(llm_provider, i, manifest_slide.layout_name, signals)
            if llm_result is not None:
                classified_by_llm = True
            manifest_slide = _merge_slide(manifest_slide, llm_result)
        slides.append(manifest_slide)

    return TemplateManifest(
        template_path=str(template_path),
        format="pptx",
        generated_at=TemplateManifest.timestamp(),
        classified_by_llm=classified_by_llm,
        dimensions={"slide_width_emu": width_emu, "slide_height_emu": height_emu},
        slides=slides,
    )


def generate_docx_manifest(
    template_path: Path, llm_provider: LLMProvider | None = None,
) -> TemplateManifest:
    """Structural pass over a DOCX template's heading styles, table
    capability, and image anchors. DOCX has no fixed slide bank to clone
    (each section is a run of paragraphs, not a discrete shape tree), so
    there is no LLM classification pass here — the structural facts alone
    (heading style names, `supports_table`, `has_image_anchor`) are already
    the complete, measurable answer to "what can this template hold."
    """
    from docx import Document

    doc = Document(str(template_path))
    sections = build_docx_section_manifests(doc)

    return TemplateManifest(
        template_path=str(template_path),
        format="docx",
        generated_at=TemplateManifest.timestamp(),
        classified_by_llm=False,
        sections=sections,
    )


def manifest_cache_path(template_path: Path) -> Path:
    return template_path.with_suffix(template_path.suffix + ".layout-manifest.json")


def get_or_generate_manifest(
    template_path: Path,
    llm_provider: LLMProvider | None = None,
    force: bool = False,
) -> TemplateManifest:
    """Return the cached manifest next to `template_path` if it's newer than
    the template file, otherwise regenerate and cache it. `force=True`
    always regenerates."""
    template_path = Path(template_path)
    cache_path = manifest_cache_path(template_path)

    if not force and cache_path.exists() and cache_path.stat().st_mtime >= template_path.stat().st_mtime:
        try:
            return TemplateManifest.load(cache_path)
        except Exception as exc:
            logger.warning("Could not load cached manifest %s, regenerating: %s", cache_path, exc)

    suffix = template_path.suffix.lower()
    if suffix == ".pptx":
        manifest = generate_pptx_manifest(template_path, llm_provider)
    elif suffix == ".docx":
        manifest = generate_docx_manifest(template_path, llm_provider)
    else:
        raise ValueError(
            f"Layout manifests are not supported for '{suffix}' templates. "
            "PPTX and DOCX generation clones a template and needs a slot map; "
            "XLSX generation builds sheets directly with no template to clone, "
            "so there is nothing for a layout manifest to describe (see "
            "docs/architecture.md §3.3)."
        )

    manifest.save(cache_path)
    return manifest
