"""
Validation Pipeline.

Programmatic checks run after rendering to verify:
- No markdown artifacts remain in text runs
- No empty placeholders (e.g., template text still present)
- File size heuristics (PPTX with background images should be > 200KB)
- Basic structure integrity

A separate LLM-guided validation can optionally be triggered for semantic checks.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import ValidationIssue, ValidationResult

logger = logging.getLogger(__name__)

MARKDOWN_ARTIFACTS = ["***", "**", "__"]
KNOWN_TEMPLATE_PLACEHOLDERS = [
    "Section Name Here",
    "SECTION Number",
    "Video Name",
    "Video Number",
    "Multi Point Slide",
    "SINGLE POINT SLIDE",
    "Key Highlights",
    "Key Element Title",
    "Name of the Next Video",
    "A key point (or issue)!",
    "+80%",
    "That\u2019s how much",
]

PPTX_MIN_SIZE_BYTES = 50_000


class ProgrammaticValidator:
    """
    Runs programmatic post-render checks on generated files.
    """

    def validate_pptx(self, output_path: Path) -> ValidationResult:
        """
        Validate a generated PPTX file.

        Checks:
        - File size heuristic (background preservation)
        - No markdown artifacts in runs
        - No known template placeholder text remaining

        Args:
            output_path: Path to the .pptx file.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(passed=True)

        if not output_path.exists():
            result.add_issue("error", str(output_path), "Output file does not exist")
            return result

        # File size check
        file_size = output_path.stat().st_size
        if file_size < PPTX_MIN_SIZE_BYTES:
            result.add_issue(
                "warning",
                str(output_path),
                f"File size {file_size} bytes is below {PPTX_MIN_SIZE_BYTES} — "
                "backgrounds may be missing (check slide cloning).",
            )
        else:
            logger.info("PPTX size check passed: %d bytes", file_size)

        try:
            from pptx import Presentation

            prs = Presentation(str(output_path))
            for slide_idx, slide in enumerate(prs.slides, start=1):
                for shape in slide.shapes:
                    if not shape.has_text_frame:
                        continue
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            text = run.text

                            # Check for residual markdown artifacts
                            for artifact in MARKDOWN_ARTIFACTS:
                                if artifact in text:
                                    result.add_issue(
                                        "warning",
                                        f"Slide {slide_idx} / shape '{shape.name}'",
                                        f"Markdown artifact '{artifact}' found in: '{text[:60]}'",
                                    )

                            # Check for unreplaced template placeholders
                            for placeholder in KNOWN_TEMPLATE_PLACEHOLDERS:
                                if placeholder in text:
                                    result.add_issue(
                                        "warning",
                                        f"Slide {slide_idx} / shape '{shape.name}'",
                                        f"Template placeholder not replaced: '{placeholder}'",
                                    )

        except Exception as exc:
            result.add_issue("error", str(output_path), f"Could not open PPTX for validation: {exc}")

        if result.passed and not result.issues:
            logger.info("PPTX validation passed: %s", output_path.name)
        else:
            logger.warning(
                "PPTX validation found %d issue(s) in %s",
                len(result.issues),
                output_path.name,
            )
        return result

    def validate_docx(self, output_path: Path) -> ValidationResult:
        """
        Validate a generated DOCX file.

        Args:
            output_path: Path to the .docx file.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(passed=True)

        if not output_path.exists():
            result.add_issue("error", str(output_path), "Output file does not exist")
            return result

        try:
            from docx import Document

            doc = Document(str(output_path))

            # Check for empty document
            if not doc.paragraphs:
                result.add_issue("warning", str(output_path), "DOCX has no paragraphs")

            # Check runs for artifacts
            for para_idx, para in enumerate(doc.paragraphs):
                for run in para.runs:
                    for artifact in MARKDOWN_ARTIFACTS:
                        if artifact in run.text:
                            result.add_issue(
                                "warning",
                                f"Paragraph {para_idx}",
                                f"Markdown artifact '{artifact}' found: '{run.text[:60]}'",
                            )

        except Exception as exc:
            result.add_issue("error", str(output_path), f"Could not open DOCX for validation: {exc}")

        if result.passed and not result.issues:
            logger.info("DOCX validation passed: %s", output_path.name)
        return result

    def validate_xlsx(self, output_path: Path) -> ValidationResult:
        """
        Validate a generated XLSX file.

        Args:
            output_path: Path to the .xlsx file.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(passed=True)

        if not output_path.exists():
            result.add_issue("error", str(output_path), "Output file does not exist")
            return result

        try:
            import openpyxl

            wb = openpyxl.load_workbook(str(output_path))
            if not wb.sheetnames:
                result.add_issue("warning", str(output_path), "XLSX has no sheets")
        except Exception as exc:
            result.add_issue("error", str(output_path), f"Could not open XLSX for validation: {exc}")

        if result.passed and not result.issues:
            logger.info("XLSX validation passed: %s", output_path.name)
        return result

    def print_report(self, result: ValidationResult) -> None:
        """Print a human-readable validation report."""
        if result.passed and not result.issues:
            print("  Validation: PASSED (no issues)")
            return

        status = "PASSED" if result.passed else "FAILED"
        print(f"  Validation: {status} — {len(result.issues)} issue(s)")
        for issue in result.issues:
            print(f"    [{issue.severity.upper()}] {issue.location}: {issue.message}")
