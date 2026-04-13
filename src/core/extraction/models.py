"""
Domain models for extracted template styles and layout information.

These models capture the visual identity of DOCX and PPTX templates so that
the generation engines can re-apply exact styling to new content.

Design note: We use plain dataclasses (not Pydantic) to stay consistent with
the rest of text2officeprocessor and avoid adding a mandatory dependency.
JSON serialization is handled by a dedicated helper.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------

@dataclass
class FontProperties:
    """Character-level font properties extracted from a style definition."""
    name: str | None = None
    size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: str | None = None
    strike: bool | None = None
    color: str | None = None          # hex "#RRGGBB"
    highlight: str | None = None
    small_caps: bool | None = None
    all_caps: bool | None = None
    spacing_pt: float | None = None
    kern_pt: float | None = None


@dataclass
class ParagraphFormat:
    """Paragraph-level formatting extracted from a style definition."""
    alignment: str | None = None      # LEFT | CENTER | RIGHT | JUSTIFY
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    line_spacing: float | None = None
    line_spacing_rule: str | None = None
    indent_left_pt: float | None = None
    indent_right_pt: float | None = None
    indent_first_line_pt: float | None = None
    indent_hanging_pt: float | None = None
    keep_with_next: bool | None = None
    keep_together: bool | None = None
    page_break_before: bool | None = None


@dataclass
class ThemeInfo:
    """Theme fonts and colors extracted from theme1.xml / slideMaster."""
    major_font: str | None = None     # heading font family
    minor_font: str | None = None     # body font family
    colors: dict[str, str] = field(default_factory=dict)  # name → "#RRGGBB"


# ---------------------------------------------------------------------------
# DOCX-specific models
# ---------------------------------------------------------------------------

@dataclass
class DocxStyle:
    """A single named style extracted from a DOCX template."""
    style_id: str
    name: str
    style_type: str                   # "paragraph" | "character" | "table"
    based_on: str | None = None
    next_style: str | None = None
    is_builtin: bool = False
    is_default: bool = False
    font: FontProperties | None = None
    paragraph_format: ParagraphFormat | None = None


@dataclass
class NumberingLevel:
    """One level of a list numbering definition."""
    level: int
    num_format: str                   # "decimal" | "bullet" | "lowerLetter" | ...
    level_text: str                   # "%1." | "•" | ...
    start: int = 1
    indent_left_pt: float | None = None
    hanging_pt: float | None = None


@dataclass
class NumberingDef:
    """A concrete numbering instance with its level definitions."""
    num_id: int
    abstract_num_id: int
    levels: list[NumberingLevel] = field(default_factory=list)


@dataclass
class SectionProperties:
    """Page layout from a DOCX section."""
    page_width_pt: float | None = None
    page_height_pt: float | None = None
    margin_top_pt: float | None = None
    margin_bottom_pt: float | None = None
    margin_left_pt: float | None = None
    margin_right_pt: float | None = None
    orientation: str = "portrait"
    columns: int = 1


# ---------------------------------------------------------------------------
# PPTX-specific models
# ---------------------------------------------------------------------------

@dataclass
class PlaceholderInfo:
    """A single placeholder shape in a PPTX slide layout."""
    idx: int
    type: str                         # "title" | "body" | "subtitle" | "picture" | ...
    name: str = ""
    left_emu: int = 0
    top_emu: int = 0
    width_emu: int = 0
    height_emu: int = 0
    font: FontProperties | None = None

    @property
    def left_pt(self) -> float:
        return self.left_emu / 12700.0

    @property
    def top_pt(self) -> float:
        return self.top_emu / 12700.0

    @property
    def width_pt(self) -> float:
        return self.width_emu / 12700.0

    @property
    def height_pt(self) -> float:
        return self.height_emu / 12700.0


@dataclass
class PptxSlideLayout:
    """Extracted layout information for a single slide in the template bank."""
    index: int
    name: str
    placeholders: list[PlaceholderInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Root container
# ---------------------------------------------------------------------------

@dataclass
class ExtractedStyleSheet:
    """
    Root container for all extracted template style data.

    This is the JSON-serializable equivalent of edgemint's StyleSheet model,
    extended to support both DOCX and PPTX templates.
    """
    schema_version: str = "text2officeprocessor/v1"
    format: str = ""                  # "docx" | "pptx"
    source_file: str = ""
    extracted_at: str = ""
    tool_version: str = "0.3.0"

    # DOCX fields
    styles: list[DocxStyle] = field(default_factory=list)
    numbering_defs: list[NumberingDef] = field(default_factory=list)
    section_properties: SectionProperties | None = None

    # PPTX fields
    slide_layouts: list[PptxSlideLayout] = field(default_factory=list)
    slide_width_emu: int = 0
    slide_height_emu: int = 0

    # Shared
    theme: ThemeInfo = field(default_factory=ThemeInfo)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string, omitting None values for readability."""
        return json.dumps(
            _strip_none(asdict(self)),
            indent=indent,
            ensure_ascii=False,
        )

    def save(self, path: Path) -> Path:
        """Write JSON to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @staticmethod
    def timestamp() -> str:
        """ISO-8601 timestamp for extraction metadata."""
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_none(obj: Any) -> Any:
    """Recursively remove None values and empty collections from a dict tree."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_strip_none(item) for item in obj]
    return obj
