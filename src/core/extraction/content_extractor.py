"""
Content Extractor — reverse pipeline: Office files → Markdown + media.

Supports three extraction paths:
- DOCX → Markdown (Pandoc preferred, python-docx fallback)
- PPTX → canonical slides markdown
- XLSX → Markdown tables

Inspired by edgemint's ``extract_document_bundle`` for DOCX, extended for
PPTX and XLSX round-trip editing workflows.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from src.core.exceptions import InputFormatError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_content(
    source_path: Path,
    output_dir: Path,
    *,
    extract_styles: bool = True,
    extract_media: bool = True,
) -> Path:
    """
    Extract content, styles, and media from an Office file.

    Args:
        source_path: Path to .docx, .pptx, or .xlsx file.
        output_dir: Directory to write extracted files.
        extract_styles: Also write styles.json alongside content.
        extract_media: Also extract embedded images to media/.

    Returns:
        Path to the primary extracted content file.
    """
    source_path = Path(source_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = source_path.suffix.lower()
    if suffix == ".docx":
        content_path = _extract_docx(source_path, output_dir, extract_media)
    elif suffix == ".pptx":
        content_path = _extract_pptx(source_path, output_dir, extract_media)
    elif suffix == ".xlsx":
        content_path = _extract_xlsx(source_path, output_dir)
    else:
        raise InputFormatError(
            f"Unsupported format '{suffix}' for extraction. Use .docx, .pptx, or .xlsx."
        )

    if extract_styles:
        from src.core.extraction.style_extractor import extract_styles as _extract
        try:
            ss = _extract(source_path)
            styles_name = "pptx_styles.json" if suffix == ".pptx" else "styles.json"
            ss.save(output_dir / styles_name)
            logger.info("Styles written to %s", styles_name)
        except Exception as exc:
            logger.warning("Could not extract styles: %s", exc)

    return content_path


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def _extract_docx(docx_path: Path, output_dir: Path, extract_media: bool) -> Path:
    """Extract DOCX → content.md (+ media/)."""
    content_path = output_dir / "content.md"

    if extract_media:
        _extract_docx_media(docx_path, output_dir / "media")

    if _has_pandoc():
        _pandoc_docx_to_md(docx_path, content_path, output_dir / "media")
        logger.info("DOCX extracted via Pandoc → %s", content_path.name)
    else:
        md = _fallback_docx_to_md(docx_path)
        content_path.write_text(md, encoding="utf-8")
        logger.info("DOCX extracted via python-docx fallback → %s", content_path.name)

    return content_path


def _extract_docx_media(docx_path: Path, media_dir: Path) -> int:
    """Copy embedded images from DOCX ZIP to media/ directory."""
    media_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with ZipFile(docx_path) as archive:
            for info in archive.infolist():
                if info.filename.startswith("word/media/"):
                    target = media_dir / Path(info.filename).name
                    with archive.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    count += 1
    except Exception as exc:
        logger.warning("Could not extract DOCX media: %s", exc)
    return count


def _pandoc_docx_to_md(docx_path: Path, md_path: Path, media_dir: Path) -> None:
    """Use Pandoc to convert DOCX → Markdown with fenced divs for custom styles."""
    cmd = [
        "pandoc",
        str(docx_path),
        "-f", "docx",
        "-t", "markdown+fenced_divs+bracketed_spans+yaml_metadata_block",
        "--wrap=none",
        f"--extract-media={media_dir}",
        "-o", str(md_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.warning("Pandoc DOCX extraction failed: %s", result.stderr)
        # Fall back to python-docx
        md = _fallback_docx_to_md(docx_path)
        md_path.write_text(md, encoding="utf-8")


def _fallback_docx_to_md(docx_path: Path) -> str:
    """Extract DOCX content to Markdown using python-docx (no Pandoc)."""
    try:
        from docx import Document
    except ImportError:
        return f"<!-- python-docx not installed, cannot extract {docx_path.name} -->"

    doc = Document(str(docx_path))
    lines: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            lines.append("")
            continue

        style_name = (para.style.name or "").lower()
        if "heading 1" in style_name:
            lines.append(f"# {text}")
        elif "heading 2" in style_name:
            lines.append(f"## {text}")
        elif "heading 3" in style_name:
            lines.append(f"### {text}")
        elif "heading 4" in style_name:
            lines.append(f"#### {text}")
        elif "list bullet" in style_name or "list number" in style_name:
            lines.append(f"- {text}")
        elif "title" in style_name:
            lines.append(f"# {text}")
        elif "subtitle" in style_name:
            lines.append(f"## {text}")
        else:
            lines.append(text)

    # Tables
    for table in doc.tables:
        lines.append("")
        headers = [cell.text.strip() for cell in table.rows[0].cells]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# PPTX extraction
# ---------------------------------------------------------------------------

def _extract_pptx(pptx_path: Path, output_dir: Path, extract_media: bool) -> Path:
    """Extract PPTX → slides.md in canonical format."""
    try:
        from pptx import Presentation
    except ImportError:
        content_path = output_dir / "slides.md"
        content_path.write_text(
            f"<!-- python-pptx not installed, cannot extract {pptx_path.name} -->\n",
            encoding="utf-8",
        )
        return content_path

    prs = Presentation(str(pptx_path))
    lines: list[str] = []
    lines.append(f"# {pptx_path.stem}")
    lines.append("")

    if extract_media:
        _extract_pptx_media(pptx_path, output_dir / "media")

    for idx, slide in enumerate(prs.slides, start=1):
        layout_name = "Unknown"
        template_index = 0
        if slide.slide_layout:
            layout_name = slide.slide_layout.name or "Unknown"
            # Find layout index in the slide master
            try:
                master = slide.slide_layout.slide_master
                for li, layout in enumerate(master.slide_layouts):
                    if layout == slide.slide_layout:
                        template_index = li
                        break
            except Exception:
                pass

        lines.append(f"## SLIDE {idx} — template_index: {template_index} ({layout_name})")

        # Extract text from all shapes
        title_text = ""
        bullet_texts: list[str] = []

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue

            # Heuristic: first non-empty shape is title, rest are bullets
            if not title_text and shape.is_placeholder:
                ph = shape.placeholder_format
                if ph and ph.idx == 0:
                    title_text = text
                    continue

            if not title_text:
                title_text = text
                continue

            # Multi-paragraph shapes become separate bullets
            for para in shape.text_frame.paragraphs:
                pt = para.text.strip()
                if pt:
                    # Strip existing bullet markers
                    if pt.startswith(("\u2022 ", "- ", "* ")):
                        pt = pt[2:]
                    bullet_texts.append(pt)

        if title_text:
            lines.append(f'- placeholder: "Title" \u2192 "{title_text}"')

        if bullet_texts:
            lines.append("- bullets:")
            for bt in bullet_texts:
                lines.append(f'  - "{bt}"')

        # Slide notes
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"<!-- notes: {notes} -->")

        lines.append("")

    content_path = output_dir / "slides.md"
    content_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("PPTX extracted: %d slides → %s", len(prs.slides), content_path.name)
    return content_path


def _extract_pptx_media(pptx_path: Path, media_dir: Path) -> int:
    """Copy embedded images from PPTX ZIP to media/ directory."""
    media_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with ZipFile(pptx_path) as archive:
            for info in archive.infolist():
                if info.filename.startswith("ppt/media/"):
                    target = media_dir / Path(info.filename).name
                    with archive.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    count += 1
    except Exception as exc:
        logger.warning("Could not extract PPTX media: %s", exc)
    return count


# ---------------------------------------------------------------------------
# XLSX extraction
# ---------------------------------------------------------------------------

def _extract_xlsx(xlsx_path: Path, output_dir: Path) -> Path:
    """Extract XLSX → content.md with Markdown tables per sheet."""
    try:
        import openpyxl
    except ImportError:
        content_path = output_dir / "content.md"
        content_path.write_text(
            f"<!-- openpyxl not installed, cannot extract {xlsx_path.name} -->\n",
            encoding="utf-8",
        )
        return content_path

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    lines: list[str] = []
    lines.append(f"# {xlsx_path.stem}")
    lines.append("")

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        lines.append(f"## {sheet_name}")
        lines.append("")

        rows_data: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c for c in cells):
                rows_data.append(cells)

        if not rows_data:
            lines.append("*Empty sheet*")
            lines.append("")
            continue

        # First row as header
        max_cols = max(len(r) for r in rows_data)
        # Pad rows to uniform width
        for r in rows_data:
            while len(r) < max_cols:
                r.append("")

        headers = rows_data[0]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    content_path = output_dir / "content.md"
    content_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("XLSX extracted: %d sheets → %s", len(wb.sheetnames), content_path.name)
    return content_path


# ---------------------------------------------------------------------------
# Pandoc detection
# ---------------------------------------------------------------------------

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
