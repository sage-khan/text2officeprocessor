"""
Input Preprocessor — converts .md / .txt / .html to ParsedDocument.

Responsibilities:
- Detect and validate input format
- Normalize encoding and whitespace
- Extract headings, paragraphs, lists, tables, images
- Produce a ParsedDocument instance
"""

import logging
import re
from pathlib import Path
from typing import Any

from src.core.exceptions import InputFormatError
from src.core.models import (
    ContentBlock,
    ContentType,
    DocumentSection,
    ParsedDocument,
)

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".md", ".txt", ".html", ".htm"}

# Markdown artifact tokens to strip from text runs
MARKDOWN_ARTIFACTS = ["***", "**", "__", "---", "*"]


def _strip_artifacts(text: str) -> str:
    """Remove markdown formatting tokens from a text string."""
    for token in MARKDOWN_ARTIFACTS:
        text = text.replace(token, "")
    return text.strip()


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple blank lines and normalize line endings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class InputPreprocessor:
    """Parses .md, .txt, and .html files into a ParsedDocument."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse the input file and return a structured ParsedDocument.

        Args:
            file_path: Absolute path to the input file.

        Returns:
            ParsedDocument with extracted sections and content blocks.

        Raises:
            InputFormatError: If the file does not exist or format is unsupported.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise InputFormatError(f"Input file not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise InputFormatError(
                f"Unsupported format '{suffix}'. Supported: {SUPPORTED_FORMATS}"
            )

        logger.info("Parsing input file: %s", file_path)
        raw_text = file_path.read_text(encoding="utf-8", errors="replace")
        normalized = _normalize_whitespace(raw_text)

        if suffix in {".md", ".txt"}:
            return self._parse_markdown(file_path, normalized)
        return self._parse_html(file_path, normalized)

    # ------------------------------------------------------------------
    # Markdown / plain-text parsing
    # ------------------------------------------------------------------

    def _parse_markdown(self, file_path: Path, text: str) -> ParsedDocument:
        lines = text.split("\n")
        title = self._extract_title_from_md(lines) or file_path.stem
        sections: list[DocumentSection] = []
        current_section: DocumentSection | None = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Heading detection
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                # Level 1 headings become top-level section titles
                if level == 1 and current_section is None:
                    # Document title — already captured
                    i += 1
                    continue
                if current_section is not None:
                    sections.append(current_section)
                current_section = DocumentSection(title=heading_text, level=level)
                i += 1
                continue

            if current_section is None:
                current_section = DocumentSection(title="", level=1)

            # Table detection (lines starting with |)
            if line.strip().startswith("|") and i + 1 < len(lines):
                table_lines, i = self._consume_table(lines, i)
                if table_lines:
                    table_data = self._parse_md_table(table_lines)
                    current_section.content.append(
                        ContentBlock(
                            content_type=ContentType.TABLE,
                            data=table_data,
                            raw="\n".join(table_lines),
                        )
                    )
                continue

            # List detection
            if re.match(r"^(\s*[-*+]|\s*\d+\.)\s+", line):
                list_items, i = self._consume_list(lines, i)
                current_section.content.append(
                    ContentBlock(
                        content_type=ContentType.LIST,
                        data=list_items,
                        raw="\n".join(list_items),
                    )
                )
                continue

            # Image detection: ![alt](path)
            img_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
            if img_match:
                current_section.content.append(
                    ContentBlock(
                        content_type=ContentType.IMAGE,
                        data={"alt": img_match.group(1), "path": img_match.group(2)},
                        raw=line.strip(),
                    )
                )
                i += 1
                continue

            # Non-empty paragraph
            stripped = line.strip()
            if stripped:
                current_section.content.append(
                    ContentBlock(
                        content_type=ContentType.PARAGRAPH,
                        data=_strip_artifacts(stripped),
                        raw=stripped,
                    )
                )

            i += 1

        if current_section is not None and (
            current_section.content or current_section.title
        ):
            sections.append(current_section)

        doc = ParsedDocument(
            title=title,
            source_path=file_path,
            source_format=file_path.suffix.lstrip(".").lower(),
            sections=sections,
        )
        logger.info("Parsed %d sections from %s", len(sections), file_path.name)
        return doc

    def _extract_title_from_md(self, lines: list[str]) -> str:
        """Extract the first H1 heading as document title."""
        for line in lines:
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                return m.group(1).strip()
        return ""

    def _consume_list(self, lines: list[str], start: int) -> tuple[list[str], int]:
        """Collect consecutive list item lines."""
        items: list[str] = []
        i = start
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^\s*[-*+]\s+(.+)$", line)
            if not m:
                m = re.match(r"^\s*\d+\.\s+(.+)$", line)
            if m:
                items.append(_strip_artifacts(m.group(1).strip()))
                i += 1
            elif not line.strip():
                i += 1
                break
            else:
                break
        return items, i

    def _consume_table(self, lines: list[str], start: int) -> tuple[list[str], int]:
        """Collect all lines belonging to a markdown table."""
        table_lines: list[str] = []
        i = start
        while i < len(lines) and (lines[i].strip().startswith("|") or re.match(r"^\s*[-|:]+\s*$", lines[i])):
            table_lines.append(lines[i])
            i += 1
        return table_lines, i

    def _parse_md_table(self, lines: list[str]) -> dict[str, Any]:
        """Parse a markdown table into headers + rows."""
        rows = []
        for line in lines:
            if re.match(r"^\s*[-|:]+\s*$", line):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            return {"headers": [], "rows": []}
        return {"headers": rows[0], "rows": rows[1:]}

    # ------------------------------------------------------------------
    # HTML parsing (basic — strips tags)
    # ------------------------------------------------------------------

    def _parse_html(self, file_path: Path, text: str) -> ParsedDocument:
        """Minimal HTML parser: strips tags and delegates to markdown parser."""
        try:
            from html.parser import HTMLParser

            class _TextExtractor(HTMLParser):
                def __init__(self) -> None:
                    super().__init__()
                    self.chunks: list[str] = []
                    self._skip = False

                def handle_starttag(self, tag: str, attrs: list) -> None:
                    if tag in {"script", "style"}:
                        self._skip = True
                    if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "br", "tr"}:
                        self.chunks.append("\n")

                def handle_endtag(self, tag: str) -> None:
                    if tag in {"script", "style"}:
                        self._skip = False
                    if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"}:
                        self.chunks.append("\n")

                def handle_data(self, data: str) -> None:
                    if not self._skip:
                        self.chunks.append(data)

            extractor = _TextExtractor()
            extractor.feed(text)
            plain = "".join(extractor.chunks)
            plain = _normalize_whitespace(plain)
        except Exception as exc:
            logger.warning("HTML parsing failed, using raw text: %s", exc)
            plain = re.sub(r"<[^>]+>", " ", text)
            plain = _normalize_whitespace(plain)

        # Delegate plain text to markdown parser
        tmp_path = file_path.with_suffix(".md")
        return self._parse_markdown(file_path, plain)
