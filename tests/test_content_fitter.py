"""
Tests for PPTXContentFitter — overflow handling strategies (summarize/split/shrink/auto).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.core.engines.pptx.content_fitter import (
    OverflowConfig,
    PPTXContentFitter,
    load_fitter_config,
)
from src.core.models import (
    SlideContent,
    SlideDefinition,
    SlideIntent,
    SlidePlan,
)


def make_config(**overrides) -> OverflowConfig:
    cfg = OverflowConfig(
        strategy="split",
        max_body_chars=400,
        max_bullet_chars=40,
        max_slide_total_chars=120,
        max_bullets_per_slide=3,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


# ---------------------------------------------------------------------------
# fit_content — "no fitting needed" path
# ---------------------------------------------------------------------------

def test_content_within_limits_is_unchanged():
    fitter = PPTXContentFitter(config=make_config())
    content = SlideContent(title="Short Slide", bullets=["Point one", "Point two"])

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert result[0].title == "Short Slide"
    assert result[0].bullets == ["Point one", "Point two"]
    assert result[0].notes == "No fitting needed"


def test_needs_fitting_triggers_on_bullet_count():
    cfg = make_config(max_bullets_per_slide=2, max_slide_total_chars=10_000, max_bullet_chars=10_000)
    fitter = PPTXContentFitter(config=cfg)
    content = SlideContent(title="T", bullets=["a", "b", "c"])

    result = fitter.fit_content(content)

    # Strategy is "split" so we expect more than one fitted slide back.
    assert len(result) > 1


# ---------------------------------------------------------------------------
# fit_content — SPLIT strategy (pure rule-based, no LLM required)
# ---------------------------------------------------------------------------

def test_split_chunks_bullets_within_limits():
    cfg = make_config(strategy="split")
    fitter = PPTXContentFitter(config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="Dense Slide", bullets=bullets)

    result = fitter.fit_content(content)

    assert len(result) > 1
    for fitted in result:
        assert len(fitted.bullets) <= cfg.max_bullets_per_slide
        assert sum(len(b) for b in fitted.bullets) <= cfg.max_slide_total_chars or len(fitted.bullets) == 1
        assert fitted.template_index == 6


def test_split_preserves_all_bullets_across_slides():
    cfg = make_config(strategy="split")
    fitter = PPTXContentFitter(config=cfg)
    bullets = [f"Bullet {i}" for i in range(7)]
    content = SlideContent(title="T", bullets=bullets)

    result = fitter.fit_content(content)

    flattened = [b for fitted in result for b in fitted.bullets]
    assert flattened == bullets


def test_split_titles_continuation_slides():
    cfg = make_config(strategy="split")
    fitter = PPTXContentFitter(config=cfg)
    bullets = [f"Bullet number {i} with extra padding to force overflow" for i in range(8)]
    content = SlideContent(title="Quarterly Results", bullets=bullets)

    result = fitter.fit_content(content)

    assert result[0].title == "Quarterly Results"
    for fitted in result[1:]:
        assert fitted.title == "Quarterly Results (Cont'd)"


def test_split_single_chunk_keeps_original_title_and_notes():
    cfg = make_config(strategy="split", max_bullets_per_slide=10, max_slide_total_chars=10_000)
    fitter = PPTXContentFitter(config=cfg)
    # Long bullet forces "needs_fitting" via max_bullet_chars but the chunk
    # still fits on a single slide.
    content = SlideContent(title="One Slide Only", bullets=["x" * 50, "short"])

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert result[0].title == "One Slide Only"
    assert result[0].notes == "No split needed"


# ---------------------------------------------------------------------------
# fit_content — SHRINK strategy
# ---------------------------------------------------------------------------

def test_shrink_keeps_all_content_on_one_slide():
    cfg = make_config(strategy="shrink")
    fitter = PPTXContentFitter(config=cfg)
    bullets = [f"Bullet {i} padded out a bit longer" for i in range(8)]
    content = SlideContent(title="Heavy Slide", bullets=bullets, items={"k": "v"})

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert result[0].bullets == bullets
    assert result[0].items == {"k": "v"}
    assert result[0].template_index == 6
    assert "shrink" in result[0].notes.lower()


# ---------------------------------------------------------------------------
# fit_content — strategies that require an LLM fall back gracefully
# ---------------------------------------------------------------------------

def test_summarize_without_provider_falls_back_to_split():
    cfg = make_config(strategy="summarize")
    fitter = PPTXContentFitter(provider=None, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="T", bullets=bullets)

    result = fitter.fit_content(content)

    # No provider available -> falls back to splitting (multiple slides, template 6)
    assert len(result) > 1
    assert all(f.template_index == 6 for f in result)


def test_auto_without_provider_defaults_to_split():
    cfg = make_config(strategy="auto")
    fitter = PPTXContentFitter(provider=None, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="T", bullets=bullets)

    result = fitter.fit_content(content)

    assert len(result) > 1


def test_summarize_parses_llm_json_response():
    provider = MagicMock()
    provider.generate.return_value = (
        '{"slides": [{"title": "Condensed", "bullets": ["A", "B"]}], "notes": "trimmed filler"}'
    )
    cfg = make_config(strategy="summarize")
    fitter = PPTXContentFitter(provider=provider, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="Original", bullets=bullets)

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert result[0].title == "Condensed"
    assert result[0].bullets == ["A", "B"]
    assert "Summarized" in result[0].notes


def test_summarize_parses_markdown_fenced_llm_response():
    """Real models (e.g. qwen2.5vl via Ollama) commonly wrap JSON replies in
    ```json ... ``` fences — the parser must extract the object, not fall back."""
    provider = MagicMock()
    provider.generate.return_value = (
        "```json\n"
        '{"slides": [{"title": "Condensed", "bullets": ["A", "B"]}], "notes": "trimmed filler"}'
        "\n```"
    )
    cfg = make_config(strategy="summarize")
    fitter = PPTXContentFitter(provider=provider, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="Original", bullets=bullets)

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert result[0].title == "Condensed"
    assert result[0].bullets == ["A", "B"]


def test_summarize_falls_back_to_split_on_bad_json():
    provider = MagicMock()
    provider.generate.return_value = "not valid json"
    cfg = make_config(strategy="summarize")
    fitter = PPTXContentFitter(provider=provider, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="Original", bullets=bullets)

    result = fitter.fit_content(content)

    # Falls back to rule-based splitting rather than crashing.
    assert len(result) > 1
    assert all(f.template_index == 6 for f in result)


def test_auto_uses_llm_strategy_selection():
    provider = MagicMock()
    provider.generate.return_value = "shrink"
    cfg = make_config(strategy="auto")
    fitter = PPTXContentFitter(provider=provider, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="T", bullets=bullets)

    result = fitter.fit_content(content)

    assert len(result) == 1
    assert "shrink" in result[0].notes.lower()


def test_auto_ignores_unrecognised_llm_response():
    provider = MagicMock()
    provider.generate.return_value = "I dunno, maybe try something else?"
    cfg = make_config(strategy="auto")
    fitter = PPTXContentFitter(provider=provider, config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    content = SlideContent(title="T", bullets=bullets)

    result = fitter.fit_content(content)

    # Falls back to the safe "split" default when the LLM response is unusable.
    assert len(result) > 1


# ---------------------------------------------------------------------------
# fit_slide_plan — SlideDefinition <-> SlideContent round trip
# ---------------------------------------------------------------------------

def test_fit_slide_plan_preserves_first_slide_template_index():
    cfg = make_config(strategy="split")
    fitter = PPTXContentFitter(config=cfg)
    bullets = [f"Bullet number {i} with some padding text" for i in range(8)]
    plan = SlidePlan(
        title="Deck",
        slides=[
            SlideDefinition(
                slide_number=1,
                template_index=2,
                slide_type="bullets",
                intent=SlideIntent.BULLETS,
                replacements={"title": "Overflowing Slide"},
                bullets=bullets,
                image_path="photo.jpg",
            )
        ],
    )

    fitted_plan = fitter.fit_slide_plan(plan)

    assert len(fitted_plan.slides) > 1
    first, *rest = fitted_plan.slides
    # User/template-chosen index is preserved on slide 0 ...
    assert first.template_index == 2
    assert first.image_path == "photo.jpg"
    # ... but new split-off slides get the fitter's high-capacity hint and no image.
    for sdef in rest:
        assert sdef.template_index == 6
        assert sdef.image_path == ""
    # Slide numbers are sequential.
    assert [s.slide_number for s in fitted_plan.slides] == list(
        range(1, 1 + len(fitted_plan.slides))
    )


def test_fit_slide_plan_leaves_short_slides_untouched():
    cfg = make_config()
    fitter = PPTXContentFitter(config=cfg)
    plan = SlidePlan(
        title="Deck",
        slides=[
            SlideDefinition(
                slide_number=1,
                template_index=0,
                slide_type="section_header",
                intent=SlideIntent.SECTION_HEADER,
                replacements={"title": "Intro"},
                bullets=["one", "two"],
            )
        ],
    )

    fitted_plan = fitter.fit_slide_plan(plan)

    assert len(fitted_plan.slides) == 1
    assert fitted_plan.slides[0].template_index == 0
    assert fitted_plan.slides[0].bullets == ["one", "two"]


def test_fit_slide_plan_does_not_inject_spurious_title_key():
    """Regression test: a slide whose `replacements` dict has no literal
    "title" key (true for every bundled template's Key Highlights/Grid/
    Features/Benefits slide types, which key their title placeholder by its
    actual template text, not the word "title") must come back from
    `fit_slide_plan()` with no "title" key added either. Previously
    `merged_replacements = {**sdef.replacements, "title": fitted.title}`
    added one unconditionally (usually "" when no fitting was needed),
    which `_render_slide()`'s `replace_text_everywhere()` — a SUBSTRING
    matcher — then used to delete the literal text "title" wherever it
    appeared on the slide, corrupting shapes like this library's own
    "card_1_title" placeholder into "card_1_"."""
    cfg = make_config()  # strategy="split", short content needs no fitting
    fitter = PPTXContentFitter(config=cfg)
    plan = SlidePlan(
        title="Deck",
        slides=[
            SlideDefinition(
                slide_number=1,
                template_index=7,
                slide_type="key_highlights",
                intent=SlideIntent.KEY_HIGHLIGHTS,
                replacements={"Key Highlights": "Course Highlights"},
                items={"card_1_title": "Foundations", "card_1_body": "Core concepts."},
            )
        ],
    )

    fitted_plan = fitter.fit_slide_plan(plan)

    assert len(fitted_plan.slides) == 1
    fitted_sdef = fitted_plan.slides[0]
    assert "title" not in fitted_sdef.replacements
    assert fitted_sdef.replacements == {"Key Highlights": "Course Highlights"}
    assert fitted_sdef.items == {"card_1_title": "Foundations", "card_1_body": "Core concepts."}


def test_fit_slide_plan_still_updates_existing_title_key():
    """When `replacements` already carries a literal "title" key, the
    fitter's (possibly LLM-rewritten) title should still overwrite it —
    only the unconditional-injection case above is the bug."""
    cfg = make_config()
    fitter = PPTXContentFitter(config=cfg)
    plan = SlidePlan(
        title="Deck",
        slides=[
            SlideDefinition(
                slide_number=1,
                template_index=0,
                slide_type="section_header",
                intent=SlideIntent.SECTION_HEADER,
                replacements={"title": "Intro"},
            )
        ],
    )

    fitted_plan = fitter.fit_slide_plan(plan)

    assert fitted_plan.slides[0].replacements["title"] == "Intro"


# ---------------------------------------------------------------------------
# load_fitter_config — resolves via config_loader, defaults when missing
# ---------------------------------------------------------------------------

def test_load_fitter_config_returns_defaults_for_missing_path(tmp_path):
    cfg = load_fitter_config(tmp_path / "does-not-exist.yaml")

    assert cfg.strategy == "auto"
    assert cfg.max_body_chars == 400
    assert cfg.high_capacity_templates == [6, 7]


def test_load_fitter_config_reads_pptx_overflow_section(tmp_path):
    config_file = tmp_path / "rules.yaml"
    config_file.write_text(
        "pptx:\n"
        "  overflow_strategy: shrink\n"
        "  max_body_chars: 250\n"
        "  max_bullet_chars: 80\n"
        "  max_slide_total_chars: 500\n"
        "  bullets_max: 4\n"
        "  high_capacity_layouts: [5]\n",
        encoding="utf-8",
    )

    cfg = load_fitter_config(config_file)

    assert cfg.strategy == "shrink"
    assert cfg.max_body_chars == 250
    assert cfg.max_bullet_chars == 80
    assert cfg.max_slide_total_chars == 500
    assert cfg.max_bullets_per_slide == 4
    assert cfg.high_capacity_templates == [5]


def test_load_fitter_config_resolves_repo_default_without_explicit_path():
    """The bug fix: no hardcoded relative path — config_loader finds the real default."""
    cfg = load_fitter_config()

    # Whatever the current default_rules.yaml says, it must actually have been
    # read (not silently skipped) — overflow_strategy is "auto" in both the
    # repo and bundled copies.
    assert cfg.strategy == "auto"
    assert cfg.max_bullets_per_slide == 6
