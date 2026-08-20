"""
Domain models for template layout manifests.

A layout manifest is advisory metadata, never executable logic: every
`injection_recipe` value it can carry names one of this library's own
proven, human-reviewed injection functions (see the fixed enum below). An
LLM classification pass (see `manifest.py`) may pick WHICH recipe applies
to a given slot, but it can never invent a new one — a wrong LLM guess can
therefore only select the wrong-but-still-safe recipe, never construct an
unsafe operation. Structural facts (position, shape counts, run structure)
always come from direct template inspection and always win over an LLM
guess where the two conflict.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "text2officeprocessor-manifest/v1"

# The fixed enum of injection recipes a manifest may ever label a slot with.
# Every value here corresponds to a real, tested function in this codebase —
# see docs/architecture.md §5. Never add a value here that isn't backed by
# an existing, proven recipe.
INJECTION_RECIPES: frozenset[str] = frozenset({
    "single_run_replace",
    "cross_run_replace",
    "set_bullets",
    "apply_items",
    "inject_template_image",
    "docx_harden_table",
    "slidepart_clone",
    "none_supported",
})


@dataclass
class SlotManifest:
    """One editable region within a slide/section."""
    role: str
    kind: str = "placeholder"  # "placeholder" | "textbox_pattern" | "grouped_diagram"
    match_text: str = ""
    match_pattern: str = ""
    position_emu: dict[str, int] = field(default_factory=dict)
    accepts: list[str] = field(default_factory=list)  # "text" | "image" | "table"
    injection_recipe: str = ""
    aspect_ratio: float | None = None


@dataclass
class SlideManifest:
    """One slide in a PPTX template bank."""
    index: int
    layout_name: str = ""
    content_affinity: list[str] = field(default_factory=list)
    capacity: dict[str, int] = field(default_factory=dict)
    slots: list[SlotManifest] = field(default_factory=list)
    clone_strategy: str = "slidepart_clone"
    notes: str = ""


@dataclass
class SectionManifest:
    """One structural region in a DOCX template (a heading level, a table
    region, or an image-anchor paragraph)."""
    role: str
    heading_style: str | None = None
    supports_table: bool = False
    has_image_anchor: bool = False
    notes: str = ""


@dataclass
class SynthesisGuidance:
    """What to do when no existing slide/section fits a needed content shape."""
    closest_match_by_intent: dict[str, int] = field(default_factory=dict)
    xml_patterns_to_reuse: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=lambda: [
        "add_slide(layout) alone",
        "deepcopy(slide)",
        "shape.left reassignment",
        "text_frame.clear() / text_frame.text = ...",
        "slide.shapes.add_table() on a cloned slide",
    ])


@dataclass
class TemplateManifest:
    """Root manifest for one template file."""
    schema_version: str = SCHEMA_VERSION
    template_path: str = ""
    format: str = ""  # "pptx" | "docx"
    generated_at: str = ""
    classified_by_llm: bool = False
    dimensions: dict[str, int] = field(default_factory=dict)

    slides: list[SlideManifest] = field(default_factory=list)      # pptx
    sections: list[SectionManifest] = field(default_factory=list)  # docx

    synthesis_guidance: SynthesisGuidance = field(default_factory=SynthesisGuidance)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(_strip_none(asdict(self)), indent=indent, ensure_ascii=False)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @staticmethod
    def load(path: Path) -> "TemplateManifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        slides = [
            SlideManifest(
                index=s["index"],
                layout_name=s.get("layout_name", ""),
                content_affinity=s.get("content_affinity", []),
                capacity=s.get("capacity", {}),
                slots=[SlotManifest(**slot) for slot in s.get("slots", [])],
                clone_strategy=s.get("clone_strategy", "slidepart_clone"),
                notes=s.get("notes", ""),
            )
            for s in data.get("slides", [])
        ]
        sections = [SectionManifest(**sec) for sec in data.get("sections", [])]
        sg_data = data.get("synthesis_guidance", {})
        synthesis_guidance = SynthesisGuidance(
            closest_match_by_intent=sg_data.get("closest_match_by_intent", {}),
            xml_patterns_to_reuse=sg_data.get("xml_patterns_to_reuse", []),
            forbidden=sg_data.get("forbidden") or SynthesisGuidance().forbidden,
        )
        return TemplateManifest(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            template_path=data.get("template_path", ""),
            format=data.get("format", ""),
            generated_at=data.get("generated_at", ""),
            classified_by_llm=data.get("classified_by_llm", False),
            dimensions=data.get("dimensions", {}),
            slides=slides,
            sections=sections,
            synthesis_guidance=synthesis_guidance,
        )

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def best_slide_for(
        self,
        affinities: list[str],
        needs_image: bool = False,
        needs_table: bool = False,
        content_size: int = 0,
    ) -> SlideManifest | None:
        """
        Return the best-fitting SlideManifest for a content block.

        Filters to slides whose `content_affinity` intersects `affinities`,
        further filters to slides with an image/table-accepting slot if
        required, then picks the closest capacity fit (smallest capacity
        that still fits `content_size`, to avoid triggering overflow
        handling unnecessarily) — falling back to the largest-capacity
        candidate if none is big enough.
        """
        candidates = [s for s in self.slides if set(s.content_affinity) & set(affinities)]
        if not candidates:
            return None

        if needs_image:
            candidates = [s for s in candidates if any("image" in slot.accepts for slot in s.slots)] or candidates
        if needs_table:
            table_candidates = [s for s in candidates if any("table" in slot.accepts for slot in s.slots)]
            if not table_candidates:
                return None
            candidates = table_candidates

        if not content_size:
            return candidates[0]

        def _capacity(s: SlideManifest) -> int:
            return s.capacity.get("body_max_chars_per_slot") or s.capacity.get("title_max_chars") or 0

        fitting = [s for s in candidates if _capacity(s) == 0 or _capacity(s) >= content_size]
        if fitting:
            return min(fitting, key=lambda s: _capacity(s) or float("inf"))
        return max(candidates, key=_capacity)


def _strip_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_strip_none(item) for item in obj]
    return obj
