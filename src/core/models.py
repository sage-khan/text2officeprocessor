"""
Domain models for text2officeprocessor — all dataclasses that flow through the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ContentType(str, Enum):
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    HEADING = "heading"


class SlideIntent(str, Enum):
    TITLE = "title"
    BULLETS = "bullets"
    STATS = "stats"
    DIAGRAM = "diagram"
    SECTION_HEADER = "section_header"
    VIDEO_TITLE = "video_title"
    CALLOUT = "callout"
    KEY_HIGHLIGHTS = "key_highlights"
    KEY_POINTERS = "key_pointers"
    FEATURES = "features"
    BENEFITS = "benefits"
    NEXT_VIDEO = "next_video"
    GRID = "grid"
    SINGLE_POINT = "single_point"


class OutputFormat(str, Enum):
    PPTX = "pptx"
    DOCX = "docx"
    XLSX = "xlsx"


class VisualHint(str, Enum):
    NONE = "none"
    CHART = "chart"
    FLOWCHART = "flowchart"
    TABLE = "table"


# ---------------------------------------------------------------------------
# Parser output models
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    """A single block of content within a section."""
    content_type: ContentType
    data: Any
    raw: str = ""


@dataclass
class DocumentSection:
    """A named section of the parsed document."""
    title: str
    level: int
    content: list[ContentBlock] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Output of the InputPreprocessor — the canonical intermediate representation."""
    title: str
    source_path: Path
    source_format: str
    sections: list[DocumentSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Planner output models
# ---------------------------------------------------------------------------

@dataclass
class SlideContent:
    """Structured content for a single slide."""
    title: str = ""
    bullets: list[str] = field(default_factory=list)
    body: str = ""
    visual_hint: VisualHint = VisualHint.NONE
    items: dict[str, str] = field(default_factory=dict)


@dataclass
class SlideDefinition:
    """A fully resolved slide definition ready for the PPTX engine."""
    slide_number: int
    template_index: int
    slide_type: str
    intent: SlideIntent
    replacements: dict[str, str] = field(default_factory=dict)
    bullets: list[str] = field(default_factory=list)
    items: dict[str, str] = field(default_factory=dict)
    diagram_path: str = ""


@dataclass
class SlidePlan:
    """Complete slide plan output by the ContentPlanner."""
    title: str
    slides: list[SlideDefinition] = field(default_factory=list)


@dataclass
class SheetDefinition:
    """A single sheet for XLSX output."""
    name: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)


@dataclass
class SpreadsheetPlan:
    """Complete spreadsheet plan output by the ContentPlanner."""
    sheets: list[SheetDefinition] = field(default_factory=list)


@dataclass
class DocPlan:
    """Plan for DOCX output — sections with formatted content."""
    title: str
    sections: list[DocumentSection] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation models
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation issue found in output."""
    severity: str
    location: str
    message: str


@dataclass
class ValidationResult:
    """Aggregate result of the validation pipeline."""
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def add_issue(self, severity: str, location: str, message: str) -> None:
        self.issues.append(ValidationIssue(severity=severity, location=location, message=message))
        if severity == "error":
            self.passed = False
