"""
DOCX Engine — dual rendering: Pandoc (preferred) + python-docx (fallback).

Two rendering paths:
1. Pandoc with --reference-doc: preserves all template styling with high fidelity.
   Inspired by edgemint's apply.py approach.
2. Direct python-docx body injection: used when Pandoc is unavailable.
   Preserves logo/image paragraphs, injects content in document order.

Both paths strip markdown artifacts and ensure clean output.
"""

from __future__ import annotations

import copy
import logging
import subprocess
import tempfile
from pathlib import Path

from src.core.exceptions import RenderError, TemplateNotFoundError
from src.core.models import ContentType, DocPlan, DocumentSection

logger = logging.getLogger(__name__)

MARKDOWN_ARTIFACTS = ["***", "**", "__", "---"]

# Word namespace
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _strip_md_artifacts(text: str) -> str:
    """Remove markdown formatting tokens from text."""
    for artifact in MARKDOWN_ARTIFACTS:
        text = text.replace(artifact, "")
    return text.strip()


def _has_pandoc() -> bool:
    """Check if Pandoc is available on the system."""
    try:
        result = subprocess.run(
            ["pandoc", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class DOCXEngine:
    """
    Renders a DocPlan into a DOCX file by injecting content into a template.

    Two rendering paths:
    1. **Pandoc** (preferred): converts plan to Markdown, then runs
       ``pandoc --reference-doc=template.docx`` for pixel-perfect styling.
    2. **python-docx** (fallback): direct body injection when Pandoc is
       unavailable.

    Usage:
        engine = DOCXEngine()
        engine.render(doc_plan, template_path, output_path)
    """

    def __init__(self, *, use_pandoc: bool | None = None) -> None:
        """
        Args:
            use_pandoc: Force Pandoc on/off. ``None`` = auto-detect.
        """
        if use_pandoc is None:
            self._use_pandoc = _has_pandoc()
        else:
            self._use_pandoc = use_pandoc

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
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not template_path.exists():
            raise TemplateNotFoundError(f"Template not found: {template_path}")

        if self._use_pandoc:
            try:
                return self._render_via_pandoc(plan, template_path, output_path)
            except Exception as exc:
                logger.warning(
                    "Pandoc rendering failed (%s), falling back to python-docx", exc,
                )

        return self._render_via_python_docx(plan, template_path, output_path)

    # ------------------------------------------------------------------
    # Pandoc rendering path (preferred)
    # ------------------------------------------------------------------

    def _render_via_pandoc(
        self,
        plan: DocPlan,
        template_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Generate DOCX using Pandoc with the template as --reference-doc.

        This preserves all theme fonts, colors, heading styles, margins, and
        headers/footers from the template — much higher fidelity than
        python-docx body injection.
        """
        md_content = self._plan_to_markdown(plan)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(md_content)
            tmp_md = Path(tmp.name)

        try:
            cmd = [
                "pandoc",
                str(tmp_md),
                "-f", "markdown",
                "-t", "docx",
                f"--reference-doc={template_path}",
                "-o", str(output_path),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RenderError(
                    f"Pandoc exited with code {result.returncode}: {result.stderr.strip()}"
                )

            self._harden_tables(output_path)

            logger.info("DOCX rendered via Pandoc → %s", output_path.name)
            return output_path
        finally:
            tmp_md.unlink(missing_ok=True)

    @staticmethod
    def _harden_tables(docx_path: Path) -> None:
        """
        Make every table in the rendered DOCX self-contained: explicit
        borders and per-column widths written directly onto the table XML.

        Pandoc's docx writer references a table style named "Table" AND a
        paragraph style named "Compact" on every table-cell paragraph — both
        defined in Pandoc's *built-in* reference.docx, but absent from most
        user --reference-doc templates (which only ship "Normal",
        "TableNormal", etc). When LibreOffice meets a table cell whose
        paragraph references an unresolvable style, it doesn't fall back
        gracefully — it abandons the table's grid layout altogether and
        renders every cell stacked in a single column. Dropping unresolvable
        style references (and writing explicit borders/widths so the table
        still looks intentional) sidesteps style resolution entirely.
        """
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        try:
            doc = Document(str(docx_path))
        except Exception as exc:
            logger.warning("Could not reopen DOCX to harden tables: %s", exc)
            return

        if not doc.tables:
            return

        known_style_ids = {s.style_id for s in doc.styles}

        for table in doc.tables:
            tbl = table._tbl
            tblPr = tbl.tblPr

            # An unresolved <w:tblStyle> reference (Pandoc always emits
            # w:val="Table", which most reference templates don't define)
            # makes LibreOffice abandon the table's grid layout entirely.
            # Drop it — the explicit borders/widths below render the table
            # correctly without depending on any named style.
            style_el = tblPr.find(qn("w:tblStyle"))
            if style_el is not None and style_el.get(qn("w:val")) not in known_style_ids:
                tblPr.remove(style_el)

            borders = tblPr.find(qn("w:tblBorders"))
            if borders is None:
                borders = OxmlElement("w:tblBorders")
                tblPr.append(borders)
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                edge_el = borders.find(qn(f"w:{edge}"))
                if edge_el is None:
                    edge_el = OxmlElement(f"w:{edge}")
                    borders.append(edge_el)
                edge_el.set(qn("w:val"), "single")
                edge_el.set(qn("w:sz"), "4")
                edge_el.set(qn("w:space"), "0")
                edge_el.set(qn("w:color"), "auto")

            grid = tbl.find(qn("w:tblGrid"))
            grid_widths = (
                [int(gc.get(qn("w:w"))) for gc in grid.findall(qn("w:gridCol"))]
                if grid is not None else []
            )

            for row in table.rows:
                for col_idx, cell in enumerate(row.cells):
                    tcPr = cell._tc.get_or_add_tcPr()
                    tcW = tcPr.find(qn("w:tcW"))
                    if tcW is None:
                        tcW = OxmlElement("w:tcW")
                        tcPr.append(tcW)
                    if grid_widths:
                        width = grid_widths[min(col_idx, len(grid_widths) - 1)]
                    else:
                        width = 1980
                    tcW.set(qn("w:w"), str(width))
                    tcW.set(qn("w:type"), "dxa")

                    # Pandoc stamps every cell paragraph with <w:pStyle
                    # w:val="Compact"/>. If the reference template doesn't
                    # define that style, drop the reference — an unresolvable
                    # pStyle inside a table cell is what makes LibreOffice
                    # collapse the whole table's grid.
                    for para in cell.paragraphs:
                        pPr = para._p.find(qn("w:pPr"))
                        if pPr is None:
                            continue
                        pStyle = pPr.find(qn("w:pStyle"))
                        if pStyle is not None and pStyle.get(qn("w:val")) not in known_style_ids:
                            pPr.remove(pStyle)

        doc.save(str(docx_path))
        logger.debug("Hardened %d table(s) in %s", len(doc.tables), docx_path.name)

    @staticmethod
    def _plan_to_markdown(plan: DocPlan) -> str:
        """Convert a DocPlan to Markdown text suitable for Pandoc."""
        lines: list[str] = []
        if plan.title:
            lines.append(f"# {plan.title}")
            lines.append("")

        for section in plan.sections:
            if section.title:
                level = min(section.level, 6)
                prefix = "#" * level
                lines.append(f"{prefix} {section.title}")
                lines.append("")

            for block in section.content:
                if block.content_type == ContentType.PARAGRAPH:
                    text = _strip_md_artifacts(str(block.data))
                    if text:
                        lines.append(text)
                        lines.append("")

                elif block.content_type == ContentType.LIST:
                    for item in block.data:
                        lines.append(f"- {_strip_md_artifacts(str(item))}")
                    lines.append("")

                elif block.content_type == ContentType.TABLE:
                    headers = block.data.get("headers", [])
                    rows = block.data.get("rows", [])
                    if headers:
                        lines.append(
                            "| " + " | ".join(str(h) for h in headers) + " |"
                        )
                        lines.append(
                            "| " + " | ".join("---" for _ in headers) + " |"
                        )
                    for row in rows:
                        lines.append(
                            "| " + " | ".join(str(c) for c in row) + " |"
                        )
                    lines.append("")

                elif block.content_type == ContentType.HEADING:
                    lines.append(f"## {_strip_md_artifacts(str(block.data))}")
                    lines.append("")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # python-docx rendering path (fallback)
    # ------------------------------------------------------------------

    def _render_via_python_docx(
        self,
        plan: DocPlan,
        template_path: Path,
        output_path: Path,
    ) -> Path:
        """Generate DOCX via direct python-docx body injection (original method)."""
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
