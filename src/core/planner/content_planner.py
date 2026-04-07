"""
Content Planner.

Maps normalized (intent, SlideContent) pairs to concrete SlideDefinition objects
that the PPTX/DOCX/XLSX engines can consume directly.

Also handles direct parsing of the canonical 'slides markdown' format
(## SLIDE N — template_index: N (Type)) for when the user provides a pre-planned file.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.core.exceptions import PlannerError
from src.core.models import (
    DocPlan,
    DocumentSection,
    ParsedDocument,
    SheetDefinition,
    SlideContent,
    SlideDefinition,
    SlideIntent,
    SlidePlan,
    SpreadsheetPlan,
    ContentType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template index mapping: SlideIntent → default template_index
#
# The indices below map to a general-purpose 13-slide template bank.
# Users can override this mapping via a template_map config or by
# providing a --slides-md file that specifies template_index explicitly.
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATE_MAP: dict[SlideIntent, tuple[int, str]] = {
    SlideIntent.SECTION_HEADER: (0, "Section Header"),
    SlideIntent.VIDEO_TITLE: (1, "Video Title"),
    SlideIntent.SINGLE_POINT: (2, "Single Point"),
    SlideIntent.BULLETS: (3, "Multi Point"),
    SlideIntent.CALLOUT: (4, "Callout"),
    SlideIntent.STATS: (5, "Stats"),
    SlideIntent.KEY_HIGHLIGHTS: (7, "Key Highlights — 4 columns"),
    SlideIntent.FEATURES: (9, "Features 6-pill"),
    SlideIntent.BENEFITS: (10, "Benefits 6-item"),
    SlideIntent.GRID: (11, "Excellence Grid"),
    SlideIntent.NEXT_VIDEO: (12, "Next Video"),
    SlideIntent.TITLE: (0, "Section Header"),
    SlideIntent.DIAGRAM: (3, "Multi Point"),
    SlideIntent.KEY_POINTERS: (6, "Key Pointers 4-quad"),
}


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "default_rules.yaml"


def _load_placeholder_map(config_path: Path | None = None) -> dict[str, dict[str, str]]:
    """
    Load the placeholder_map section from the YAML config file.

    Falls back to an empty dict (no replacements applied) if the file is
    missing or the key is absent — this is intentional so the engine never
    crashes on a missing config.
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("placeholder_map", {})
    except Exception as exc:
        logger.warning("Could not load placeholder_map from '%s': %s", path, exc)
        return {}


class ContentPlanner:
    """
    Produces SlidePlan / DocPlan / SpreadsheetPlan from normalized content.
    """

    def __init__(
        self,
        template_map: dict[SlideIntent, tuple[int, str]] | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._template_map = template_map or DEFAULT_TEMPLATE_MAP
        self._placeholder_map = _load_placeholder_map(config_path)

    # ------------------------------------------------------------------
    # PPTX planning
    # ------------------------------------------------------------------

    def plan_slides(
        self,
        document: ParsedDocument,
        normalized: list[tuple[SlideIntent, SlideContent]],
    ) -> SlidePlan:
        """
        Build a SlidePlan from a ParsedDocument and its normalized sections.

        Args:
            document: The original ParsedDocument.
            normalized: List of (SlideIntent, SlideContent) from the normalizer.

        Returns:
            SlidePlan with one SlideDefinition per section.
        """
        if len(document.sections) != len(normalized):
            raise PlannerError(
                f"Section count mismatch: {len(document.sections)} sections "
                f"but {len(normalized)} normalized entries."
            )

        slide_defs: list[SlideDefinition] = []
        for slide_num, (section, (intent, content)) in enumerate(
            zip(document.sections, normalized), start=1
        ):
            template_index, slide_type = self._template_map.get(
                intent, (3, "Multi Point")
            )
            replacements = self._build_replacements(intent, content, slide_type)
            slide_def = SlideDefinition(
                slide_number=slide_num,
                template_index=template_index,
                slide_type=slide_type,
                intent=intent,
                replacements=replacements,
                bullets=content.bullets,
                items=content.items,
            )
            slide_defs.append(slide_def)
            logger.debug(
                "Slide %d: intent=%s template_index=%d", slide_num, intent.value, template_index
            )

        return SlidePlan(title=document.title, slides=slide_defs)

    def _build_replacements(
        self, intent: SlideIntent, content: SlideContent, slide_type: str
    ) -> dict[str, str]:
        """
        Build placeholder replacement dict based on intent and content.

        Placeholder strings are read from the placeholder_map section of
        default_rules.yaml (or the config_path supplied at construction time)
        so that no template-specific strings are hardcoded in Python.
        """
        replacements: dict[str, str] = {}
        pm = self._placeholder_map

        if intent == SlideIntent.SECTION_HEADER:
            sh = pm.get("section_header", {})
            replacements[sh.get("title", "Section Name Here")] = content.title
            replacements[sh.get("number", "SECTION Number")] = ""
        elif intent == SlideIntent.VIDEO_TITLE:
            vt = pm.get("video_title", {})
            replacements[vt.get("title", "Video Name")] = content.title
            replacements[vt.get("section", "Section Name")] = ""
            replacements[vt.get("number", "Video Number")] = ""
        elif intent == SlideIntent.BULLETS:
            bl = pm.get("bullets", {})
            replacements[bl.get("title", "Multi Point Slide")] = content.title
        elif intent == SlideIntent.SINGLE_POINT:
            sp = pm.get("single_point", {})
            replacements[sp.get("title", "SINGLE POINT SLIDE")] = content.title
            if content.body:
                replacements[sp.get("body", "Sample text here")] = content.body
        elif intent == SlideIntent.CALLOUT:
            cl = pm.get("callout", {})
            replacements[cl.get("body", "Key point here")] = content.body or content.title
        elif intent == SlideIntent.STATS:
            st = pm.get("stats", {})
            replacements[st.get("title", "Stat")] = content.title
            if content.body:
                replacements[st.get("body", "Stat description")] = content.body
        elif intent == SlideIntent.KEY_HIGHLIGHTS:
            kh = pm.get("key_highlights", {})
            replacements[kh.get("title", "Key Highlights")] = content.title
            replacements[kh.get("subtitle", "Subhead")] = ""
        elif intent == SlideIntent.NEXT_VIDEO:
            nv = pm.get("next_video", {})
            replacements[nv.get("title", "Next Video Title")] = content.title
            replacements[nv.get("label", "Next Video")] = ""
        elif intent == SlideIntent.GRID:
            gr = pm.get("grid", {})
            replacements[gr.get("title", "Grid Title")] = content.title

        return replacements

    # ------------------------------------------------------------------
    # Slides-markdown parsing (canonical input format)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_slides_markdown(md_path: Path) -> SlidePlan:
        """
        Parse a pre-authored slides markdown file into a SlidePlan.

        This is the primary input method when users provide fully specified
        slide definitions using the ## SLIDE N — template_index: N (Type) format.

        Args:
            md_path: Path to the slides markdown file.

        Returns:
            SlidePlan with fully resolved SlideDefinition objects.
        """
        text = Path(md_path).read_text(encoding="utf-8")
        lines = text.split("\n")
        slides: list[SlideDefinition] = []
        current: dict | None = None
        in_bullets = False
        pending_old: str | None = None
        slide_number = 0

        for raw_line in lines:
            line = raw_line.rstrip()

            # Handle continuation of multiline placeholder old-text
            if pending_old is not None and current is not None:
                m = re.match(r'^(.+?)"\s*→\s*"(.+?)"$', line)
                if m:
                    full_old = pending_old + "\n" + m.group(1)
                    current["replacements"][full_old] = m.group(2)
                    pending_old = None
                else:
                    pending_old += "\n" + line
                continue

            # Slide header: ## SLIDE N — template_index: N (Type)
            m = re.match(r"^## SLIDE \d+ .+ template_index: (\d+) \((.+)\)", line)
            if m:
                if current:
                    slides.append(_dict_to_slide_def(current))
                slide_number += 1
                current = {
                    "slide_number": slide_number,
                    "template_index": int(m.group(1)),
                    "slide_type": m.group(2),
                    "replacements": {},
                    "bullets": [],
                    "items": {},
                }
                in_bullets = False
                continue

            if current is None:
                continue

            if line.strip() == "---":
                in_bullets = False
                continue

            if line.strip() == "- bullets:":
                in_bullets = True
                continue

            # Single-line placeholder: - placeholder: "old" → "new"
            m = re.match(r'^- placeholder: "(.+?)"\s*→\s*"(.+?)"$', line)
            if m:
                current["replacements"][m.group(1)] = m.group(2)
                in_bullets = False
                continue

            # Multiline placeholder start: - placeholder: "EXCELLENCE IN THE
            m = re.match(r'^- placeholder: "(.+)$', line)
            if m and "→" not in line:
                pending_old = m.group(1)
                in_bullets = False
                continue

            # Card / item key-value: - card_N_title: "..." or - item_N_body: "..."
            m = re.match(r'^- (card_\d+_\w+|item_\d+_\w+|item_\d\d_\w+): "(.+?)"$', line)
            if m:
                current["items"][m.group(1)] = m.group(2)
                in_bullets = False
                continue

            # Bullet item
            if in_bullets:
                m = re.match(r'^\s+- "(.+)"$', line)
                if m:
                    current["bullets"].append(m.group(1))

        if current:
            slides.append(_dict_to_slide_def(current))

        logger.info("Parsed %d slide definitions from %s", len(slides), md_path.name)
        return SlidePlan(title=md_path.stem, slides=slides)

    # ------------------------------------------------------------------
    # DOCX planning
    # ------------------------------------------------------------------

    @staticmethod
    def plan_document(document: ParsedDocument) -> DocPlan:
        """Build a DocPlan directly from a ParsedDocument (pass-through)."""
        return DocPlan(title=document.title, sections=document.sections)

    # ------------------------------------------------------------------
    # XLSX planning
    # ------------------------------------------------------------------

    @staticmethod
    def plan_spreadsheet(document: ParsedDocument) -> SpreadsheetPlan:
        """
        Build a SpreadsheetPlan from a ParsedDocument.

        Rules:
        - Each top-level section becomes a sheet.
        - Tables within sections become rows.
        - Bullet lists become single-column rows.
        """
        sheets: list[SheetDefinition] = []

        for section in document.sections:
            sheet_name = section.title[:31] if section.title else f"Sheet{len(sheets)+1}"
            sheet = SheetDefinition(name=sheet_name)

            for block in section.content:
                if block.content_type == ContentType.TABLE:
                    table_data = block.data
                    if not sheet.columns:
                        sheet.columns = table_data.get("headers", [])
                    for row in table_data.get("rows", []):
                        sheet.rows.append(row)
                elif block.content_type == ContentType.LIST:
                    if not sheet.columns:
                        sheet.columns = [section.title or "Item"]
                    for item in block.data:
                        sheet.rows.append([item])
                elif block.content_type == ContentType.PARAGRAPH:
                    if not sheet.columns:
                        sheet.columns = ["Content"]
                    sheet.rows.append([str(block.data)])

            sheets.append(sheet)

        return SpreadsheetPlan(sheets=sheets)


def _dict_to_slide_def(data: dict) -> SlideDefinition:
    """Convert a raw parsed dict to a SlideDefinition."""
    return SlideDefinition(
        slide_number=data["slide_number"],
        template_index=data["template_index"],
        slide_type=data["slide_type"],
        intent=SlideIntent.BULLETS,
        replacements=data["replacements"],
        bullets=data["bullets"],
        items=data["items"],
    )
