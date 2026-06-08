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
        while i < len(lines) and (lines[i].strip().startswith("|") or re.match(r"^[\s|:-]+$", lines[i])):
            table_lines.append(lines[i])
            i += 1
        return table_lines, i

    def _parse_md_table(self, lines: list[str]) -> dict[str, Any]:
        """Parse a markdown table into headers + rows."""
        rows = []
        for line in lines:
            if re.match(r"^[\s|:-]+$", line):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            return {"headers": [], "rows": []}
        return {"headers": rows[0], "rows": rows[1:]}

    # ------------------------------------------------------------------
    # HTML parsing — full DOM-aware parser using lxml
    # ------------------------------------------------------------------

    def _parse_html(self, file_path: Path, text: str) -> ParsedDocument:
        """
        Parse an HTML file into a ParsedDocument using lxml.

        Handles:
        - Headings (h1–h6) → DocumentSection boundaries
        - Paragraphs (p) with inline <strong>/<em>/<a> preserved as plain text
        - Unordered and ordered lists (ul/ol → li) → ContentType.LIST
        - Tables (table → thead/tbody/tr/th/td) → ContentType.TABLE
        - Images (img[src]) → ContentType.IMAGE
        - Skips <script> and <style> blocks entirely
        """
        try:
            from lxml import html as lhtml
            root = lhtml.fromstring(text)
        except Exception as exc:
            logger.warning("lxml HTML parse failed, falling back to tag stripping: %s", exc)
            return self._parse_html_fallback(file_path, text)

        # Remove script/style nodes entirely
        for dead in root.xpath(".//script | .//style"):
            dead.getparent().remove(dead)

        title = ""
        h1_els = root.xpath(".//h1")
        if h1_els:
            title = (h1_els[0].text_content() or "").strip()
        if not title:
            title_els = root.xpath(".//title")
            title = (title_els[0].text_content() or "").strip() if title_els else file_path.stem

        sections: list[DocumentSection] = []
        current_section: DocumentSection | None = None

        HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
        HEADING_LEVEL = {f"h{n}": n for n in range(1, 7)}
        SKIP_TAGS = {"head", "script", "style", "meta", "link", "noscript"}
        BLOCK_TAGS = HEADING_TAGS | {"p", "ul", "ol", "table", "blockquote", "pre", "figure", "div", "section", "article"}

        body = root.find(".//body")
        if body is None:
            body = root

        def _inner_text(el: Any) -> str:
            """Extract all text inside an element, preserving inline spacing."""
            return (el.text_content() or "").strip()

        def _process_element(el: Any) -> None:
            nonlocal current_section

            tag = (el.tag or "").lower() if isinstance(el.tag, str) else ""

            if tag in SKIP_TAGS:
                return

            # Headings — start a new section
            if tag in HEADING_TAGS:
                level = HEADING_LEVEL[tag]
                heading_text = _inner_text(el)
                if not heading_text:
                    return
                if level == 1 and not sections and current_section is None:
                    # Document title; skip creating a section for the very first h1
                    return
                if current_section is not None and (current_section.content or current_section.title):
                    sections.append(current_section)
                current_section = DocumentSection(title=heading_text, level=level)
                return

            if current_section is None:
                current_section = DocumentSection(title="", level=1)

            # Lists
            if tag in {"ul", "ol"}:
                items = [
                    _strip_artifacts(li.text_content().strip())
                    for li in el.xpath(".//li")
                    if li.text_content().strip()
                ]
                if items:
                    current_section.content.append(ContentBlock(
                        content_type=ContentType.LIST,
                        data=items,
                        raw="\n".join(items),
                    ))
                return

            # Tables
            if tag == "table":
                headers: list[str] = []
                rows: list[list[str]] = []
                for th in el.xpath(".//thead/tr/th | .//tr[1]/th"):
                    headers.append(th.text_content().strip())
                for tr in el.xpath(".//tbody/tr | .//tr"):
                    cells = [td.text_content().strip() for td in tr.xpath(".//td")]
                    if cells:
                        rows.append(cells)
                if headers or rows:
                    current_section.content.append(ContentBlock(
                        content_type=ContentType.TABLE,
                        data={"headers": headers, "rows": rows},
                        raw=_inner_text(el),
                    ))
                return

            # Images
            if tag == "img":
                src = el.get("src", "")
                alt = el.get("alt", "")
                if src:
                    current_section.content.append(ContentBlock(
                        content_type=ContentType.IMAGE,
                        data={"alt": alt, "path": src},
                        raw=f'<img src="{src}" alt="{alt}">',
                    ))
                return

            # Paragraphs and other block text
            if tag in {"p", "blockquote", "pre", "figcaption"}:
                text_content = _inner_text(el)
                if text_content:
                    current_section.content.append(ContentBlock(
                        content_type=ContentType.PARAGRAPH,
                        data=_strip_artifacts(text_content),
                        raw=text_content,
                    ))
                return

            # Recurse into container elements
            if tag in {"div", "section", "article", "main", "header", "footer", "aside", "body"}:
                for child in el:
                    _process_element(child)

        for child in body:
            _process_element(child)

        if current_section is not None and (current_section.content or current_section.title):
            sections.append(current_section)

        doc = ParsedDocument(
            title=title,
            source_path=file_path,
            source_format="html",
            sections=sections,
        )
        logger.info("Parsed %d sections from HTML: %s", len(sections), file_path.name)
        return doc

    def _parse_html_fallback(self, file_path: Path, text: str) -> ParsedDocument:
        """Last-resort HTML parser: strips all tags and delegates to markdown parser."""
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = _normalize_whitespace(plain)
        return self._parse_markdown(file_path, plain)
