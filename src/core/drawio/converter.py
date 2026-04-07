"""
src/core/drawio/converter.py

Exports .drawio diagram files to PNG using the drawio CLI.

Requirements:
  - drawio CLI installed and on PATH (ships with the drawio desktop app)
  - xvfb-run available on headless Linux (optional; used automatically)

Usage:
    from src.core.drawio.converter import export_drawio_to_png
    png_path = export_drawio_to_png(Path("diagram.drawio"))
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DRAWIO_CMD = "drawio"
_XVFB_CMD = "xvfb-run"

# Export resolution: 2x scale keeps diagrams crisp on 96 dpi slides
_DEFAULT_SCALE = "2"
_DEFAULT_BORDER = "10"


class DrawioExportError(Exception):
    """Raised when the drawio CLI fails or is unavailable."""


def _drawio_available() -> bool:
    return shutil.which(_DRAWIO_CMD) is not None


def _xvfb_available() -> bool:
    return shutil.which(_XVFB_CMD) is not None


def export_drawio_to_png(
    drawio_path: Path,
    output_path: Path | None = None,
    page_index: int | None = None,
    scale: str = _DEFAULT_SCALE,
    border: str = _DEFAULT_BORDER,
    transparent: bool = False,
) -> Path:
    """
    Export a .drawio file to PNG using the drawio CLI.

    Args:
        drawio_path:  Path to the source .drawio file.
        output_path:  Destination PNG path. Defaults to a sibling file with .png extension.
        page_index:   1-based page number to export (default: first page).
        scale:        Resolution scale factor passed to drawio (default: "2" for 2x).
        border:       Border width in pixels around the diagram (default: "10").
        transparent:  If True, export with transparent background.

    Returns:
        Path to the written PNG file.

    Raises:
        DrawioExportError: If drawio is not installed or the export fails.
        FileNotFoundError: If drawio_path does not exist.
    """
    drawio_path = Path(drawio_path).resolve()

    if not drawio_path.exists():
        raise FileNotFoundError(f"Draw.io file not found: {drawio_path}")

    if not _drawio_available():
        raise DrawioExportError(
            "drawio CLI not found on PATH. "
            "Install the drawio desktop application or drawio CLI: "
            "https://github.com/jgraph/drawio-desktop/releases"
        )

    if output_path is None:
        output_path = drawio_path.with_suffix(".png")
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [_DRAWIO_CMD, "--export", "--format", "png",
           "--output", str(output_path),
           "--scale", scale,
           "--border", border]

    if transparent:
        cmd.append("--transparent")

    if page_index is not None:
        cmd.extend(["--page-index", str(page_index)])

    cmd.append(str(drawio_path))

    # Wrap with xvfb-run on headless Linux to provide a virtual display
    if _xvfb_available():
        cmd = [_XVFB_CMD, "--auto-servernum", "--"] + cmd

    logger.info("Exporting draw.io: %s → %s", drawio_path.name, output_path.name)
    logger.debug("Command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise DrawioExportError(f"drawio export timed out after 60 seconds: {drawio_path}")
    except Exception as exc:
        raise DrawioExportError(f"drawio export failed: {exc}") from exc

    if result.returncode != 0:
        raise DrawioExportError(
            f"drawio export failed (exit {result.returncode}) for {drawio_path.name}.\n"
            f"stderr: {result.stderr.strip()}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise DrawioExportError(
            f"drawio export produced no output for {drawio_path.name}. "
            f"Expected: {output_path}"
        )

    logger.info("Exported draw.io PNG: %s (%d bytes)", output_path.name, output_path.stat().st_size)
    return output_path


def export_all_pages(
    drawio_path: Path,
    output_dir: Path | None = None,
    scale: str = _DEFAULT_SCALE,
    border: str = _DEFAULT_BORDER,
) -> list[Path]:
    """
    Export every page in a multi-page .drawio file to separate PNGs.

    Returns a list of PNG paths in page order (page 1, page 2, ...).
    Falls back to single-page export if page count detection fails.
    """
    drawio_path = Path(drawio_path).resolve()
    if output_dir is None:
        output_dir = drawio_path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_count = _detect_page_count(drawio_path)
    logger.info("draw.io file has %d page(s): %s", page_count, drawio_path.name)

    results: list[Path] = []
    for page in range(1, page_count + 1):
        out = output_dir / f"{drawio_path.stem}-page{page}.png"
        png = export_drawio_to_png(drawio_path, out, page_index=page, scale=scale, border=border)
        results.append(png)

    return results


def _detect_page_count(drawio_path: Path) -> int:
    """Count <diagram> elements in the .drawio XML to determine page count."""
    try:
        import re
        content = drawio_path.read_text(encoding="utf-8", errors="replace")
        count = len(re.findall(r"<diagram[\s>]", content))
        return max(count, 1)
    except Exception:
        return 1
