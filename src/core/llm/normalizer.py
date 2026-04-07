"""
LLM Normalization Module.

Takes a ParsedDocument and optionally uses an LLM to:
- Assign semantic intent to each section (title, bullets, stats, etc.)
- Suggest visual hints (chart, flowchart, table)
- Produce a normalized structured representation ready for the planner

When no LLM is available, falls back to rule-based heuristics.
"""

from __future__ import annotations

import json
import logging
import re

from src.core.exceptions import LLMUnavailableError
from src.core.llm.base import LLMProvider
from src.core.models import (
    ContentType,
    DocumentSection,
    ParsedDocument,
    SlideContent,
    SlideIntent,
    VisualHint,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Prompt templates (stored here; can be moved to config/ YAML later)
# ------------------------------------------------------------------

NORMALIZE_PROMPT_TEMPLATE = """
You are a document analysis assistant. Given a section of a document, classify its intent and extract key content.

Respond with ONLY valid JSON matching this schema:
{{
  "intent": "<title|bullets|stats|diagram|section_header|video_title|callout|key_highlights|features|benefits|next_video|grid|single_point>",
  "title": "<section title>",
  "bullets": ["<bullet 1>", "<bullet 2>"],
  "body": "<paragraph text if intent is single_point or callout>",
  "visual_hint": "<none|chart|flowchart|table>"
}}

Rules:
- If the section has a numbered list, use intent "bullets"
- If the section has exactly one key statistic or number, use intent "stats"
- If the section title starts with "Video" or contains video number, use intent "video_title"
- If the section has a table, set visual_hint "table"
- Never generate layout instructions — only semantic content

Section title: {title}
Section content:
{content}
"""

# ------------------------------------------------------------------
# Rule-based heuristics (fallback when LLM unavailable)
# ------------------------------------------------------------------

SECTION_HEADER_KEYWORDS = {"introduction", "overview", "summary", "section"}
VIDEO_TITLE_KEYWORDS = {"video", "lecture", "module"}
STATS_PATTERNS = [r"\b\d+%\b", r"\$\d+", r"\b\d+x\b", r"\b\d{2,}[km]?\b"]
NEXT_VIDEO_KEYWORDS = {"next video", "next lecture", "coming up"}


def _rule_based_intent(section: DocumentSection) -> SlideIntent:
    """Determine slide intent using keyword/pattern heuristics."""
    title_lower = section.title.lower()

    if any(kw in title_lower for kw in NEXT_VIDEO_KEYWORDS):
        return SlideIntent.NEXT_VIDEO

    if any(kw in title_lower for kw in VIDEO_TITLE_KEYWORDS):
        return SlideIntent.VIDEO_TITLE

    if any(kw in title_lower for kw in SECTION_HEADER_KEYWORDS) and not section.content:
        return SlideIntent.SECTION_HEADER

    # Count list blocks
    list_blocks = [c for c in section.content if c.content_type == ContentType.LIST]
    table_blocks = [c for c in section.content if c.content_type == ContentType.TABLE]

    if table_blocks:
        return SlideIntent.BULLETS

    # Check for stat patterns in text
    all_text = " ".join(
        str(c.data) for c in section.content if c.content_type == ContentType.PARAGRAPH
    )
    if any(re.search(pat, all_text) for pat in STATS_PATTERNS):
        return SlideIntent.STATS

    if list_blocks and len(list_blocks[0].data) >= 4:
        return SlideIntent.KEY_HIGHLIGHTS

    if list_blocks:
        return SlideIntent.BULLETS

    if section.content:
        return SlideIntent.SINGLE_POINT

    return SlideIntent.TITLE


def _rule_based_visual_hint(section: DocumentSection) -> VisualHint:
    """Determine visual hint using content type."""
    for block in section.content:
        if block.content_type == ContentType.TABLE:
            return VisualHint.TABLE
        if block.content_type == ContentType.IMAGE:
            return VisualHint.CHART
    return VisualHint.NONE


def _extract_bullets_from_section(section: DocumentSection) -> list[str]:
    """Pull bullet items from all list blocks in the section."""
    bullets: list[str] = []
    for block in section.content:
        if block.content_type == ContentType.LIST:
            bullets.extend(block.data)
    return bullets


def _extract_body_from_section(section: DocumentSection) -> str:
    """Concatenate all paragraph blocks into body text."""
    parts: list[str] = []
    for block in section.content:
        if block.content_type == ContentType.PARAGRAPH:
            parts.append(str(block.data))
    return " ".join(parts)


class LLMNormalizer:
    """
    Normalizes a ParsedDocument into a list of SlideContent objects.

    Uses an LLMProvider if available, otherwise falls back to rule-based heuristics.
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def normalize(self, document: ParsedDocument) -> list[tuple[SlideIntent, SlideContent]]:
        """
        Normalize each section of a parsed document into (intent, SlideContent) pairs.

        Args:
            document: The ParsedDocument from the preprocessor.

        Returns:
            List of (SlideIntent, SlideContent) tuples, one per section.
        """
        results: list[tuple[SlideIntent, SlideContent]] = []

        for section in document.sections:
            if self._provider is not None:
                try:
                    intent, content = self._llm_normalize_section(section)
                    results.append((intent, content))
                    continue
                except LLMUnavailableError as exc:
                    logger.warning("LLM unavailable, falling back to rules: %s", exc)
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("LLM response parse error, falling back to rules: %s", exc)

            intent, content = self._rule_normalize_section(section)
            results.append((intent, content))

        logger.info("Normalized %d sections", len(results))
        return results

    def _rule_normalize_section(
        self, section: DocumentSection
    ) -> tuple[SlideIntent, SlideContent]:
        """Apply rule-based normalization to a single section."""
        intent = _rule_based_intent(section)
        visual_hint = _rule_based_visual_hint(section)
        bullets = _extract_bullets_from_section(section)
        body = _extract_body_from_section(section)

        content = SlideContent(
            title=section.title,
            bullets=bullets,
            body=body,
            visual_hint=visual_hint,
        )
        return intent, content

    def _llm_normalize_section(
        self, section: DocumentSection
    ) -> tuple[SlideIntent, SlideContent]:
        """Use an LLM to normalize a single section."""
        assert self._provider is not None

        section_text = "\n".join(
            str(block.data) for block in section.content
            if block.content_type in {ContentType.PARAGRAPH, ContentType.LIST}
        )
        prompt = NORMALIZE_PROMPT_TEMPLATE.format(
            title=section.title, content=section_text[:2000]
        )
        raw_response = self._provider.generate(prompt)

        # Extract JSON from response (handle fenced code blocks)
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in LLM response")

        data = json.loads(json_match.group(0))
        intent = SlideIntent(data.get("intent", "bullets"))
        content = SlideContent(
            title=data.get("title", section.title),
            bullets=data.get("bullets", []),
            body=data.get("body", ""),
            visual_hint=VisualHint(data.get("visual_hint", "none")),
        )
        return intent, content
