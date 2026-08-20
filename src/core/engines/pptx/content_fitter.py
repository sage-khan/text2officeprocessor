"""
PPTX Content Fitting — handles text overflow with multiple strategies.

Strategies:
1. SUMMARIZE: Use LLM to condense content while preserving key points
2. SPLIT: Distribute dense content across multiple slides
3. SHRINK: Reduce font size programmatically (original method)
4. AUTO: LLM decides based on content type

Configuration via default_rules.yaml:
  pptx:
    overflow_strategy: "auto"  # summarize | split | shrink | auto
    max_body_chars: 400
    max_bullet_chars: 120
    max_slide_total_chars: 600
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.models import SlideContent, SlideDefinition, SlideIntent, SlidePlan

logger = logging.getLogger(__name__)


@dataclass
class FittedSlide:
    """Result of content fitting - may produce multiple slides from one input."""
    title: str = ""
    bullets: list[str] = field(default_factory=list)
    items: dict[str, str] = field(default_factory=dict)
    template_index: int = 3  # Default to Multi Point
    intent: SlideIntent = SlideIntent.BULLETS
    notes: str = ""  # Fitting strategy notes for debugging


@dataclass
class OverflowConfig:
    """Configuration for overflow handling."""
    strategy: str = "auto"  # summarize | split | shrink | auto
    max_body_chars: int = 400
    max_bullet_chars: int = 120
    max_slide_total_chars: int = 600
    max_bullets_per_slide: int = 6
    high_capacity_templates: list[int] = field(default_factory=lambda: [6, 7])


class PPTXContentFitter:
    """
    Handles content overflow for PPTX slides using configurable strategies.

    The fitter analyzes content density and applies the appropriate strategy:
    - SUMMARIZE: Condense verbose content using LLM (best for dense text)
    - SPLIT: Break into multiple slides (best for many distinct points)
    - SHRINK: Reduce font size (fallback, may hurt readability)
    - AUTO: Let LLM decide based on content analysis
    """

    def __init__(
        self,
        provider: Any | None = None,
        config: OverflowConfig | None = None,
    ) -> None:
        """
        Args:
            provider: LLMProvider for summarize/auto strategies
            config: OverflowConfig with strategy and thresholds
        """
        self._provider = provider
        self._config = config or OverflowConfig()

    def fit_content(self, slide_content: SlideContent) -> list[FittedSlide]:
        """
        Fit slide content within template constraints.

        Args:
            slide_content: The content to fit (title, bullets, items).

        Returns:
            List of FittedSlide objects (may be 1 or multiple if split).
        """
        # Calculate content metrics
        total_chars = sum(len(b) for b in slide_content.bullets)
        total_chars += len(slide_content.title)
        bullet_count = len(slide_content.bullets)
        max_bullet_len = max((len(b) for b in slide_content.bullets), default=0)

        logger.debug(
            "Fitting content: %d chars, %d bullets, max bullet %d chars",
            total_chars,
            bullet_count,
            max_bullet_len,
        )

        # Determine if fitting is needed
        needs_fitting = (
            total_chars > self._config.max_slide_total_chars
            or bullet_count > self._config.max_bullets_per_slide
            or max_bullet_len > self._config.max_bullet_chars
        )

        if not needs_fitting:
            logger.debug("Content fits without fitting")
            return [
                FittedSlide(
                    title=slide_content.title,
                    bullets=slide_content.bullets[:],
                    items=slide_content.items.copy() if slide_content.items else {},
                    template_index=3,  # Multi Point
                    intent=SlideIntent.BULLETS,
                    notes="No fitting needed",
                )
            ]

        # Apply fitting strategy
        strategy = self._config.strategy
        if strategy == "auto" and self._provider:
            strategy = self._llm_select_strategy(slide_content)
            logger.info("Auto-selected strategy: %s", strategy)

        if strategy == "summarize" and self._provider:
            return self._fit_summarize(slide_content)
        elif strategy == "split":
            return self._fit_split(slide_content)
        elif strategy == "shrink":
            return self._fit_shrink(slide_content)
        else:
            # Default to split if no LLM or unknown strategy
            logger.warning(
                "Strategy '%s' unavailable (no LLM or unknown), using split",
                strategy,
            )
            return self._fit_split(slide_content)

    def fit_slide_plan(self, plan: SlidePlan) -> SlidePlan:
        """
        Fit all slides in a SlidePlan.

        Args:
            plan: Original slide plan with potentially oversized content.

        Returns:
            New SlidePlan with fitted slides (may have more slides than input).
        """
        fitted_definitions: list[SlideDefinition] = []

        for sdef in plan.slides:
            # Convert SlideDefinition to SlideContent for fitting
            slide_content = SlideContent(
                title=sdef.replacements.get("title", ""),
                bullets=sdef.bullets[:],
                items=sdef.items.copy() if sdef.items else {},
            )

            # Fit the content
            fitted_slides = self.fit_content(slide_content)

            # Convert back to SlideDefinition(s).
            # The first slide always keeps the user/template-chosen
            # template_index — the fitter's `template_index` is only a
            # generic "high-capacity layout" hint for genuinely NEW slides
            # produced by splitting (i > 0); applying it to slide 0 would
            # silently override the user's template choice even when no
            # fitting occurred (FittedSlide defaults template_index to 3).
            for i, fitted in enumerate(fitted_slides):
                # Only overlay the fitted title back onto a literal "title"
                # replacement key when one already existed on this slide —
                # unconditionally injecting {"title": fitted.title} here
                # (previously always, even when fitted.title was just an
                # echo of an absent "" default) fed an empty-string value
                # into replace_text_everywhere()'s SUBSTRING match, silently
                # deleting the literal text "title" wherever it appeared on
                # the slide — corrupting shapes like "card_1_title" into
                # "card_1_" on every render with an LLM provider configured
                # (real, high-impact defect found verifying 0.5.2's
                # apply_items() fix; no bundled template's placeholder_map
                # actually uses "title" as a literal key, so this was
                # silently active on essentially every default `convert`
                # invocation with a reachable LLM provider).
                merged_replacements = dict(sdef.replacements)
                if "title" in sdef.replacements:
                    merged_replacements["title"] = fitted.title
                new_sdef = SlideDefinition(
                    slide_number=sdef.slide_number + i,
                    template_index=sdef.template_index if i == 0 else fitted.template_index,
                    slide_type=sdef.slide_type,
                    intent=fitted.intent if i > 0 else sdef.intent,
                    replacements=merged_replacements,
                    bullets=fitted.bullets,
                    items=fitted.items,
                    diagram_path=sdef.diagram_path,
                    image_path=sdef.image_path if i == 0 else "",
                )
                fitted_definitions.append(new_sdef)

        return SlidePlan(
            title=plan.title,
            slides=fitted_definitions,
            notes=plan.notes,
        )

    # -------------------------------------------------------------------------
    # Strategy: LLM Auto-Selection
    # -------------------------------------------------------------------------

    def _llm_select_strategy(self, content: SlideContent) -> str:
        """Use LLM to select the best fitting strategy."""
        if not self._provider:
            return "split"

        prompt = f"""You are a presentation design expert. Analyze this slide content and select the best overflow handling strategy.

Content:
Title: {content.title}
Bullets:
{chr(10).join(f"- {b[:100]}" for b in content.bullets[:8])}

Metrics:
- Total characters: {sum(len(b) for b in content.bullets)}
- Bullet count: {len(content.bullets)}
- Max bullet length: {max((len(b) for b in content.bullets), default=0)} chars

Strategies:
1. "summarize" - Condense verbose text, preserve key metrics (best for dense paragraphs)
2. "split" - Break into 2-3 slides with related content (best for many distinct points)
3. "shrink" - Keep all content, reduce font size (fallback, hurts readability)

Select the SINGLE best strategy. Consider:
- If bullets are long paragraphs → summarize
- If many short bullets (8+) → split
- If mixed content → split

Respond with ONLY one word: summarize | split | shrink
"""

        try:
            response = self._provider.generate(prompt).strip().lower()
            if response in ("summarize", "split", "shrink"):
                return response
        except Exception as exc:
            logger.warning("LLM strategy selection failed: %s", exc)

        return "split"  # Safe default

    # -------------------------------------------------------------------------
    # Strategy: SUMMARIZE (LLM-powered condensation)
    # -------------------------------------------------------------------------

    def _fit_summarize(self, content: SlideContent) -> list[FittedSlide]:
        """Use LLM to condense content while preserving key points."""
        if not self._provider:
            logger.warning("Summarize strategy requires LLM, falling back to split")
            return self._fit_split(content)

        bullets_text = "\n".join(f"- {b}" for b in content.bullets)

        prompt = f"""Condense the following slide content to fit presentation constraints.

Original Title: {content.title}
Original Content:
{bullets_text}

Constraints:
- Maximum {self._config.max_bullets_per_slide} bullet points
- Maximum {self._config.max_bullet_chars} characters per bullet
- Preserve ALL numbers, percentages, and key metrics
- Remove filler words and redundant explanations
- Split into multiple slides ONLY if content truly cannot be condensed

Rules:
1. KEEP: Revenue figures, growth rates, headcount, any $ or % values
2. CONDENSE: Explanatory text to essential phrases
3. REMOVE: "This is", "We have", "There are" type filler
4. RETURN: Concise, presentation-ready bullets

Output format: JSON
{{
  "slides": [
    {{
      "title": "Condensed title (keep core meaning)",
      "bullets": ["Bullet 1", "Bullet 2", ...]
    }}
  ],
  "notes": "Brief note on what was condensed"
}}

Return ONLY the JSON, no other text."""

        try:
            response = self._provider.generate(prompt)
            # Models often wrap JSON in ```json fences or prose, so extract
            # the first {...} object rather than parsing the raw response.
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("No JSON object found in LLM response", response, 0)
            data = json.loads(json_match.group(0))
            slides_data = data.get("slides", [])

            fitted_slides: list[FittedSlide] = []
            for slide_data in slides_data:
                fitted = FittedSlide(
                    title=slide_data.get("title", content.title),
                    bullets=slide_data.get("bullets", [])[
                        : self._config.max_bullets_per_slide
                    ],
                    items=content.items.copy() if content.items else {},
                    template_index=6,  # High-capacity layout
                    intent=SlideIntent.BULLETS,
                    notes=f"Summarized: {data.get('notes', '')}",
                )
                fitted_slides.append(fitted)

            logger.info(
                "Summarized %d bullets into %d slides",
                len(content.bullets),
                len(fitted_slides),
            )
            return fitted_slides

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM summarize response: %s", exc)
            return self._fit_split(content)
        except Exception as exc:
            logger.error("Summarize strategy failed: %s", exc)
            return self._fit_split(content)

    # -------------------------------------------------------------------------
    # Strategy: SPLIT (Distribute across multiple slides)
    # -------------------------------------------------------------------------

    def _fit_split(self, content: SlideContent) -> list[FittedSlide]:
        """Split dense content across multiple slides."""
        bullets = content.bullets[:]
        fitted_slides: list[FittedSlide] = []

        # Group bullets into chunks that fit constraints
        current_chunk: list[str] = []
        current_chars = 0

        for bullet in bullets:
            bullet_chars = len(bullet)

            # Check if adding this bullet would exceed limits
            would_exceed = (
                len(current_chunk) >= self._config.max_bullets_per_slide
                or current_chars + bullet_chars > self._config.max_slide_total_chars
            )

            if would_exceed and current_chunk:
                # Create slide from current chunk
                fitted = FittedSlide(
                    title=self._split_title(content.title, len(fitted_slides) + 1),
                    bullets=current_chunk[:],
                    items=(content.items.copy() if content.items and not fitted_slides else {}),
                    template_index=6,  # High-capacity layout
                    intent=SlideIntent.BULLETS,
                    notes=f"Part {len(fitted_slides) + 1} of split content",
                )
                fitted_slides.append(fitted)

                # Start new chunk
                current_chunk = [bullet]
                current_chars = bullet_chars
            else:
                current_chunk.append(bullet)
                current_chars += bullet_chars

        # Don't forget the last chunk
        if current_chunk:
            fitted = FittedSlide(
                title=self._split_title(content.title, len(fitted_slides) + 1),
                bullets=current_chunk[:],
                items=(content.items.copy() if content.items and not fitted_slides else {}),
                template_index=6,
                intent=SlideIntent.BULLETS,
                notes=f"Part {len(fitted_slides) + 1} of split content",
            )
            fitted_slides.append(fitted)

        # If we only have one slide, keep original title
        if len(fitted_slides) == 1:
            fitted_slides[0].title = content.title
            fitted_slides[0].notes = "No split needed"

        logger.info(
            "Split %d bullets into %d slides",
            len(bullets),
            len(fitted_slides),
        )
        return fitted_slides

    def _split_title(self, base_title: str, part_num: int) -> str:
        """Generate title for split slide."""
        if part_num == 1:
            return base_title
        return f"{base_title} (Cont'd)"

    # -------------------------------------------------------------------------
    # Strategy: SHRINK (Reduce font size programmatically)
    # -------------------------------------------------------------------------

    def _fit_shrink(self, content: SlideContent) -> list[FittedSlide]:
        """
        Mark content for font shrinking.

        Note: Actual font shrinking happens in the engine via fit_text_to_shape().
        This strategy just flags that shrinking is acceptable.
        """
        return [
            FittedSlide(
                title=content.title,
                bullets=content.bullets[:],
                items=content.items.copy() if content.items else {},
                template_index=6,  # High-capacity layout
                intent=SlideIntent.BULLETS,
                notes="Shrink strategy: reduce font size if needed",
            )
        ]


# -------------------------------------------------------------------------
# Configuration loader
# -------------------------------------------------------------------------

def load_fitter_config(config_path: Path | None = None) -> OverflowConfig:
    """
    Load fitter configuration from the rules YAML.

    Resolution is delegated to ``config_loader.load_config()``, which finds
    the repo-local config during development and the bundled package config
    when installed — an explicit ``config_path`` overrides both.
    """
    from src.core.config_loader import load_config

    config = OverflowConfig()
    data = load_config(config_path)
    pptx_config = data.get("pptx", {})

    if pptx_config:
        config.strategy = pptx_config.get("overflow_strategy", config.strategy)
        config.max_body_chars = pptx_config.get("max_body_chars", config.max_body_chars)
        config.max_bullet_chars = pptx_config.get("max_bullet_chars", config.max_bullet_chars)
        config.max_slide_total_chars = pptx_config.get(
            "max_slide_total_chars", config.max_slide_total_chars
        )
        config.max_bullets_per_slide = pptx_config.get("bullets_max", config.max_bullets_per_slide)
        config.high_capacity_templates = pptx_config.get(
            "high_capacity_layouts", config.high_capacity_templates
        )

    return config
