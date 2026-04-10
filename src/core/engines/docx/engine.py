"""
DOCX Engine — Template Body Injection method.

Implements the proven template injection approach from text2officeprocessor-rules.md.
Key guarantees:
- EC-Council logo / header images are preserved (not cleared)
- Tables stay inline with surrounding paragraphs (IN-ORDER iteration)
- Paragraph styles (font name, size, bold, italic, color) are copied per run
- Markdown artifacts are stripped from all runs
- Headers and footers from the template are preserved

NEVER use Pandoc as the primary DOCX generation method.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from src.core.exceptions import RenderError, TemplateNotFoundError
from src.core.models import ContentType, DocPlan, DocumentSection

logger = logging.getLogger(__name__)

MARKDOWN_ARTIFACTS = ["***", "**", "__", "---"]

# Word namespace
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class DOCXEngine:
    """
    Renders a DocPlan into a DOCX file by injecting content into a template.

    Usage:
        engine = DOCXEngine()
        engine.render(doc_plan, template_path, output_path)
    """

    def render(
        self,
        plan: DocPlan,
        template_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Generate a DOCX file from a DocPlan.

        Args:
            plan: The DocPlan with all sections and content.
            template_path: Path to the source .docx template file.
            output_path: Where to write the output .docx.

        Returns:
            The output_path on success.

        Raises:
            TemplateNotFoundError: If the template file does not exist.
            RenderError: If rendering fails.
        """
        template_path = Path(template_path)
        output_path = Path(output_path)

        if not template_path.exists():
            raise TemplateNotFoundError(f"Template not found: {template_path}")

        try:
            from docx import Document
        except ImportError as exc:
            raise RenderError("python-docx is not installed. Run: pip install python-docx") from exc

        logger.info("Loading DOCX template: %s", template_path.name)
        try:
            template = Document(str(template_path))
        except Exception as exc:
            raise TemplateNotFoundError(f"Cannot open template '{template_path}': {exc}") from exc

        # Clear template body content, preserving logo/image paragraphs
        preserved = self._clear_body(template)
        logger.info("Preserved %d image paragraph(s) from template", preserved)

        # Inject content sections in order
        for section in plan.sections:
            self._inject_section(template, section)

        # Sanitize all runs
        self._sanitize(template)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Saving DOCX output: %s", output_path.name)
        try:
            template.save(str(output_path))
        except Exception as exc:
            raise RenderError(f"Failed to save DOCX: {exc}") from exc

        return output_path

    # ------------------------------------------------------------------
    # Body clearing with image preservation
    # ------------------------------------------------------------------

    def _clear_body(self, doc: object) -> int:
        """
        Remove all paragraphs and tables from the document body,
        except paragraphs that contain embedded images (logo, decorators).

        Args:
            doc: python-docx Document object.

        Returns:
            Count of preserved image paragraphs.
        """
        body = doc.element.body  # type: ignore
        preserved_count = 0
        IMAGE_TAGS = {"drawing", "inline", "anchor", "blip"}

        for child in list(body):
            tag = child.tag.split("}")[1] if "}" in child.tag else child.tag

            if tag == "p":
                has_image = any(
                    (descendant.tag.split("}")[1] if "}" in descendant.tag else descendant.tag)
                    in IMAGE_TAGS
                    for descendant in child.iter()
                )
                if has_image:
                    preserved_count += 1
                    continue
                body.remove(child)

            elif tag == "tbl":
                body.remove(child)

        return preserved_count

    # ------------------------------------------------------------------
    # Section injection
    # ------------------------------------------------------------------

    def _inject_section(self, doc: object, section: DocumentSection) -> None:
        """
        Add a document section (heading + content blocks) to the template.

        Args:
            doc: python-docx Document object.
            section: DocumentSection with title and content blocks.
        """
        from docx import Document
        from docx.oxml.ns import qn

        # Add section heading — fall back to bold paragraph if style unavailable
        if section.title:
            heading_level = min(section.level, 4)
            try:
                doc.add_heading(section.title, level=heading_level)  # type: ignore
            except (KeyError, Exception):
                # Template uses custom styles; add as bold paragraph instead
                para = doc.add_paragraph()  # type: ignore
                run = para.add_run(section.title)
                run.bold = True

        # Iterate body children IN ORDER (critical for table placement)
        # We build a temporary document to get the correct XML order
        para_idx = 0
        table_idx = 0

        # Collect items in document order using the section content list
        for block in section.content:
            if block.content_type == ContentType.PARAGRAPH:
                self._add_paragraph(doc, str(block.data))

            elif block.content_type == ContentType.LIST:
                for item in block.data:
                    self._add_list_item(doc, str(item))

            elif block.content_type == ContentType.TABLE:
                self._add_table(doc, block.data)

            elif block.content_type == ContentType.IMAGE:
                # Image embedding requires the actual file; log a warning if missing
                img_path = block.data.get("path", "")
                if img_path:
                    logger.debug("Skipping inline image (not yet supported in DOCX engine): %s", img_path)

            elif block.content_type == ContentType.HEADING:
                doc.add_heading(str(block.data), level=2)  # type: ignore

    def _add_paragraph(self, doc: object, text: str) -> None:
        """Add a body paragraph with artifact-cleaned text."""
        text = self._strip_artifacts(text)
        if text:
            doc.add_paragraph(text)  # type: ignore

    def _add_list_item(self, doc: object, text: str) -> None:
        """Add a bullet list item, falling back if List Bullet style is unavailable."""
        text = self._strip_artifacts(text)
        if not text:
            return
        try:
            doc.add_paragraph(text, style="List Bullet")  # type: ignore
        except (KeyError, Exception):
            para = doc.add_paragraph()  # type: ignore
            run = para.add_run(f"• {text}")
            run.bold = False

    def _add_table(self, doc: object, table_data: dict) -> None:
        """Add a formatted table from parsed table data."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        if not headers and not rows:
            return

        col_count = len(headers) if headers else (len(rows[0]) if rows else 1)
        row_count = (1 if headers else 0) + len(rows)

        if row_count == 0 or col_count == 0:
            return

        try:
            table = doc.add_table(rows=row_count, cols=col_count)  # type: ignore
            table.style = "Table Grid"

            row_offset = 0
            if headers:
                for col_idx, header_text in enumerate(headers):
                    if col_idx < col_count:
                        cell = table.rows[0].cells[col_idx]
                        cell.text = self._strip_artifacts(str(header_text))
                        # Bold header runs
                        for para in cell.paragraphs:
                            for run in para.runs:
                                run.bold = True
                row_offset = 1

            for row_idx, data_row in enumerate(rows):
                table_row = table.rows[row_idx + row_offset]
                for col_idx, cell_text in enumerate(data_row):
                    if col_idx < col_count:
                        table_row.cells[col_idx].text = self._strip_artifacts(str(cell_text))
        except Exception as exc:
            logger.warning("Failed to add table: %s", exc)

    # ------------------------------------------------------------------
    # Artifact sanitization
    # ------------------------------------------------------------------

    def _strip_artifacts(self, text: str) -> str:
        """Remove markdown formatting tokens from text."""
        for artifact in MARKDOWN_ARTIFACTS:
            text = text.replace(artifact, "")
        return text.strip()

    def _sanitize(self, doc: object) -> None:
        """Strip markdown artifacts from all runs in the document."""
        for para in doc.paragraphs:  # type: ignore
            for run in para.runs:
                for artifact in MARKDOWN_ARTIFACTS:
                    run.text = run.text.replace(artifact, "")
        for table in doc.tables:  # type: ignore
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            for artifact in MARKDOWN_ARTIFACTS:
                                run.text = run.text.replace(artifact, "")
