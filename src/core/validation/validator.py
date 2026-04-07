"""
Validation Pipeline.

Programmatic checks run after rendering to verify:
- No markdown artifacts remain in text runs
- No empty placeholders (e.g., template text still present)
- File size heuristics (PPTX with background images should be > 200KB)
- Basic structure integrity

LLMValidator provides an optional semantic coherence pass after rendering:
- Checks whether slide/section titles are meaningful
- Flags truncated or garbled bullet text
- Detects obvious content mismatches between placeholder intent and replacement text
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.config_loader import get, load_config
from src.core.models import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from src.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in fallback defaults (used when config key is absent or config is empty)
# ---------------------------------------------------------------------------
_DEFAULT_MARKDOWN_ARTIFACTS = ["***", "**", "__"]
_DEFAULT_KNOWN_PLACEHOLDERS = [
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
_DEFAULT_PPTX_MIN_SIZE_BYTES = 50_000
_DEFAULT_MAX_CONTENT_CHARS = 8_000

_DEFAULT_LLM_PROMPT = """\
You are a quality-control assistant for office document generation.

You will receive the extracted text content of a rendered document (PPTX, DOCX, or XLSX).
Analyse the content and identify any of the following problems:

1. TRUNCATED — A text run appears cut off mid-sentence or mid-word.
2. GARBLED — A text run contains incoherent, scrambled, or clearly wrong text.
3. PLACEHOLDER_LEAK — An unreplaced template placeholder is still visible (e.g. "Section Name Here", "Video Name").
4. MISMATCH — The content of a section/slide does not match its heading or title.
5. EMPTY_SECTION — A slide or section has a title but no body content at all.

Respond ONLY with a JSON array. Each element must have:
  - "severity": "warning" or "error"
  - "location": a short description of where the issue is (e.g. "Slide 3 / title", "Section: Introduction")
  - "issue_type": one of TRUNCATED | GARBLED | PLACEHOLDER_LEAK | MISMATCH | EMPTY_SECTION
  - "message": a brief, factual description of the problem

If there are no problems, respond with an empty array: []

Document content:
---
{content}
---
"""


class ProgrammaticValidator:
    """
    Runs programmatic post-render checks on generated files.

    Args:
        config_path: Optional path to a custom rules YAML. When ``None``,
                     the default config is located automatically.
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._cfg = load_config(config_path)
        vcfg = self._cfg.get("validation", {})
        self.markdown_artifacts: list[str] = vcfg.get(
            "markdown_artifacts", _DEFAULT_MARKDOWN_ARTIFACTS
        )
        self.known_placeholders: list[str] = vcfg.get(
            "known_placeholders", _DEFAULT_KNOWN_PLACEHOLDERS
        )
        self.pptx_min_size_bytes: int = vcfg.get(
            "pptx_min_size_bytes", _DEFAULT_PPTX_MIN_SIZE_BYTES
        )
        self.check_artifacts: bool = vcfg.get("check_artifacts", True)
        self.check_placeholders: bool = vcfg.get("check_placeholders", True)
        self.check_file_size: bool = vcfg.get("check_file_size", True)

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
        if self.check_file_size and file_size < self.pptx_min_size_bytes:
            result.add_issue(
                "warning",
                str(output_path),
                f"File size {file_size} bytes is below {self.pptx_min_size_bytes} — "
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
                            if self.check_artifacts:
                                for artifact in self.markdown_artifacts:
                                    if artifact in text:
                                        result.add_issue(
                                            "warning",
                                            f"Slide {slide_idx} / shape '{shape.name}'",
                                            f"Markdown artifact '{artifact}' found in: '{text[:60]}'",
                                        )

                            # Check for unreplaced template placeholders
                            if self.check_placeholders:
                                for placeholder in self.known_placeholders:
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
                    for artifact in (self.markdown_artifacts if self.check_artifacts else []):
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


# ---------------------------------------------------------------------------
# LLM Semantic Validator helpers
# ---------------------------------------------------------------------------


def _extract_pptx_text(path: Path) -> str:
    """Extract all text from a PPTX file, structured by slide."""
    from pptx import Presentation
    prs = Presentation(str(path))
    lines: list[str] = []
    for idx, slide in enumerate(prs.slides, start=1):
        lines.append(f"=== Slide {idx} ===")
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    lines.append(text)
    return "\n".join(lines)


def _extract_docx_text(path: Path) -> str:
    """Extract all paragraph text from a DOCX file."""
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_xlsx_text(path: Path) -> str:
    """Extract all cell values from an XLSX file."""
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True)
    lines: list[str] = []
    for sheet in wb.worksheets:
        lines.append(f"=== Sheet: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _parse_llm_response(response: str) -> list[dict]:
    """Extract the JSON array from the LLM response, tolerating markdown fences."""
    text = response.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # Last resort: find the first [...] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


class LLMValidator:
    """
    Optional post-render semantic validation using an LLM provider.

    Checks the extracted text content of a rendered document for:
    - Truncated or garbled text runs
    - Unreplaced template placeholders
    - Content/heading mismatches
    - Empty sections

    Falls back to a no-op (returns empty ValidationResult) if the provider
    is unavailable or the LLM call fails, so it never blocks the pipeline.

    Args:
        provider: An LLMProvider instance.
        config_path: Optional path to a custom rules YAML.  When ``None``, the
                     default config is used.  The ``llm_validation`` block in
                     the config controls the prompt template and content limit.
    """

    def __init__(
        self,
        provider: "LLMProvider",
        config_path: Path | str | None = None,
    ) -> None:
        self._provider = provider
        cfg = load_config(config_path)
        llm_cfg = cfg.get("llm_validation", {})
        self._max_content_chars: int = int(
            llm_cfg.get("max_content_chars", _DEFAULT_MAX_CONTENT_CHARS)
        )
        self._prompt_template: str = str(
            llm_cfg.get("prompt", _DEFAULT_LLM_PROMPT)
        ).strip()

    def validate(self, output_path: Path) -> ValidationResult:
        """
        Run the LLM semantic validation pass on a rendered output file.

        Args:
            output_path: Path to the rendered .pptx, .docx, or .xlsx file.

        Returns:
            ValidationResult populated with any semantic issues found.
            Always returns a result — never raises.
        """
        result = ValidationResult(passed=True)
        suffix = output_path.suffix.lower()

        try:
            if suffix == ".pptx":
                content = _extract_pptx_text(output_path)
            elif suffix in {".docx", ".doc"}:
                content = _extract_docx_text(output_path)
            elif suffix == ".xlsx":
                content = _extract_xlsx_text(output_path)
            else:
                logger.warning("LLMValidator: unsupported file type '%s' — skipping.", suffix)
                return result
        except Exception as exc:
            logger.warning("LLMValidator: could not extract text from %s: %s", output_path.name, exc)
            return result

        if not content.strip():
            logger.info("LLMValidator: no text content found in %s — skipping.", output_path.name)
            return result

        max_chars = self._max_content_chars
        truncated = content[:max_chars]
        if len(content) > max_chars:
            logger.info(
                "LLMValidator: content truncated from %d to %d chars for prompt.",
                len(content), max_chars,
            )

        prompt = self._prompt_template.format(content=truncated)

        try:
            logger.info("LLMValidator: calling provider for semantic check on %s", output_path.name)
            response = self._provider.generate(prompt)
        except Exception as exc:
            logger.warning("LLMValidator: LLM call failed — %s. Skipping semantic check.", exc)
            return result

        issues = _parse_llm_response(response)
        for item in issues:
            severity = str(item.get("severity", "warning")).lower()
            location = str(item.get("location", "unknown"))
            issue_type = str(item.get("issue_type", ""))
            message = str(item.get("message", ""))
            full_message = f"[{issue_type}] {message}" if issue_type else message
            result.add_issue(severity, location, full_message)

        logger.info(
            "LLMValidator: found %d issue(s) in %s", len(issues), output_path.name
        )
        return result
