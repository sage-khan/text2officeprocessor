"""
LLM-powered Spreadsheet Reorganizer.

Converts fragmented ParsedDocument sections into logical Excel table structures.
Uses LLM to consolidate related data into coherent sheets rather than
creating one sheet per section.

Inspired by: edgemint's structured data approach + opendataloader's
hybrid AI processing model.
"""
from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.models import (
    ContentType,
    ParsedDocument,
    SheetDefinition,
    SpreadsheetPlan,
)

logger = logging.getLogger(__name__)


@dataclass
class ReorganizedSheet:
    """A sheet definition produced by the LLM reorganizer."""
    name: str
    sheet_type: str  # dashboard | breakdown | timeline | comparison | matrix | raw
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    description: str = ""


class SpreadsheetReorganizer:
    """
    Uses LLM to reorganize document content into logical Excel tables.

    Instead of creating 1 sheet per section (which produces fragmented output),
    this consolidates related data into coherent business tables.

    Example transformations:
    - "Executive Summary" bullets → Dashboard sheet with KPIs
    - "By Region" + "By Product" tables → Consolidated breakdown sheet
    - Multiple risk matrices → Single risk overview matrix
    """

    def __init__(self, provider: Any | None = None, config: dict | None = None) -> None:
        """
        Args:
            provider: LLMProvider for AI-powered reorganization (None = rule-based)
            config: Configuration dict with keys like "enabled", "max_sheets", etc.
        """
        self._provider = provider
        self._config = config or {}
        self._enabled = self._config.get("enabled", True)
        self._max_sheets = self._config.get("max_sheets", 10)

    def reorganize(self, document: ParsedDocument) -> SpreadsheetPlan:
        """
        Convert a ParsedDocument into a consolidated SpreadsheetPlan.

        If LLM is available and enabled, uses AI to create logical table structure.
        Otherwise falls back to rule-based consolidation.

        Args:
            document: The parsed document with sections and content blocks.

        Returns:
            A SpreadsheetPlan with consolidated sheets.
        """
        if not self._enabled:
            logger.info("SpreadsheetReorganizer disabled, using raw section mapping")
            return self._rule_based_reorganize(document)

        if self._provider is None:
            logger.info("No LLM provider, using rule-based consolidation")
            return self._rule_based_reorganize(document)

        try:
            return self._llm_reorganize(document)
        except Exception as exc:
            logger.warning(
                "LLM reorganization failed (%s), falling back to rule-based", exc
            )
            return self._rule_based_reorganize(document)

    def _llm_reorganize(self, document: ParsedDocument) -> SpreadsheetPlan:
        """Use LLM to intelligently reorganize document into logical tables."""
        # Convert document to JSON-serializable structure
        doc_json = self._document_to_json(document)

        # Load prompt template from config
        prompt_template = self._config.get(
            "prompt",
            self._default_prompt()
        )

        prompt = prompt_template.format(document_json=json.dumps(doc_json, indent=2))

        logger.info("Calling LLM for spreadsheet reorganization...")
        response = self._provider.generate(prompt)

        # Parse LLM response — models often wrap JSON in ```json fences or
        # prose, so extract the first {...} object rather than parsing raw.
        try:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON object found in LLM response")
            data = json.loads(json_match.group(0))
            sheets_data = data.get("sheets", [])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse LLM response as JSON: %s", exc)
            raise

        # Convert to SheetDefinition objects
        sheets: list[SheetDefinition] = []
        for sheet_data in sheets_data[:self._max_sheets]:
            sheet = SheetDefinition(
                name=sheet_data.get("name", f"Sheet{len(sheets)+1}")[:31],
                columns=sheet_data.get("columns", []),
                rows=[
                    [str(cell) if cell is not None else "" for cell in row]
                    for row in sheet_data.get("rows", [])
                ],
            )
            sheets.append(sheet)

        logger.info(
            "LLM reorganized %d sections into %d logical sheets",
            len(document.sections),
            len(sheets),
        )
        return SpreadsheetPlan(sheets=sheets)

    def _rule_based_reorganize(self, document: ParsedDocument) -> SpreadsheetPlan:
        """
        Rule-based consolidation without LLM.

        Groups sections by content type and creates logical sheets:
        - KPI sections → Dashboard
        - Table sections with same headers → Consolidated breakdown
        - List sections → Single-column sheets
        """
        sheets: list[SheetDefinition] = []
        dashboard_data: list[list[str]] = []

        # Collect KPIs for potential dashboard
        for section in document.sections:
            kpi_rows = self._extract_kpis(section)
            if kpi_rows:
                dashboard_data.extend(kpi_rows)

        # Create Dashboard sheet if we have KPIs
        if dashboard_data:
            dashboard_sheet = SheetDefinition(
                name="Dashboard",
                columns=["Metric", "Value"],
                rows=dashboard_data[:50],  # Limit rows
            )
            sheets.append(dashboard_sheet)
            logger.debug("Created Dashboard sheet with %d KPIs", len(dashboard_data))

        # Process tables - consolidate those with similar structure
        table_groups: dict[str, list[tuple[str, dict]]] = {}
        for section in document.sections:
            for block in section.content:
                if block.content_type == ContentType.TABLE:
                    table_key = self._table_fingerprint(block.data)
                    table_groups.setdefault(table_key, []).append(
                        (section.title or "Data", block.data)
                    )

        # Create consolidated sheets for table groups
        for table_key, tables in table_groups.items():
            if len(tables) == 1:
                # Single table - create dedicated sheet
                title, table_data = tables[0]
                sheet = self._table_to_sheet(title, table_data)
                sheets.append(sheet)
            else:
                # Multiple similar tables - consolidate
                sheet = self._consolidate_tables(tables)
                sheets.append(sheet)
                logger.debug(
                    "Consolidated %d similar tables into sheet '%s'",
                    len(tables),
                    sheet.name,
                )

        # Process remaining sections (lists and paragraphs)
        for section in document.sections:
            has_table = any(
                b.content_type == ContentType.TABLE for b in section.content
            )
            if has_table:
                continue  # Already processed

            list_items: list[list[str]] = []
            paragraph_items: list[list[str]] = []

            for block in section.content:
                if block.content_type == ContentType.LIST:
                    for item in block.data:
                        list_items.append([str(item)])
                elif block.content_type == ContentType.PARAGRAPH:
                    text = str(block.data).strip()
                    if text:
                        paragraph_items.append([text])

            if list_items:
                sheets.append(SheetDefinition(
                    name=(section.title or "Items")[:31],
                    columns=["Item"],
                    rows=list_items,
                ))
            elif paragraph_items:
                # Create a text content sheet for paragraphs
                sheets.append(SheetDefinition(
                    name=(section.title or "Content")[:31],
                    columns=["Text"],
                    rows=paragraph_items,
                ))

        # Limit total sheets
        if len(sheets) > self._max_sheets:
            logger.warning(
                "Limiting sheets from %d to %d (config: max_sheets)",
                len(sheets),
                self._max_sheets,
            )
            sheets = sheets[: self._max_sheets]

        return SpreadsheetPlan(sheets=sheets)

    def _extract_kpis(self, section: Any) -> list[list[str]]:
        """Extract key metrics from section content (e.g., 'Revenue: $12.4M')."""
        kpis: list[list[str]] = []
        for block in section.content:
            if block.content_type == ContentType.PARAGRAPH:
                text = str(block.data)
                # Look for metric patterns like "Revenue: $12.4M (+28%)"
                import re
                # Pattern: Label: Value (optional change)
                match = re.match(
                    r"(.+?)[:\-]\s*(\$?[\d,.]+[KMB]?\s*(?:\([+-]?\d+%\))?)",
                    text.strip(),
                )
                if match:
                    kpis.append([match.group(1).strip(), match.group(2).strip()])
            elif block.content_type == ContentType.LIST:
                for item in block.data:
                    text = str(item)
                    import re
                    match = re.match(
                        r"(.+?)[:\-]\s*(\$?[\d,.]+[KMB]?\s*(?:\([+-]?\d+%\))?)",
                        text.strip(),
                    )
                    if match:
                        kpis.append([match.group(1).strip(), match.group(2).strip()])
        return kpis

    def _table_fingerprint(self, table_data: dict) -> str:
        """Generate a fingerprint for table structure to group similar tables."""
        headers = tuple(table_data.get("headers", []))
        return f"cols:{len(headers)}:headers:{headers}"

    def _table_to_sheet(self, title: str, table_data: dict) -> SheetDefinition:
        """Convert a single table to a SheetDefinition."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        return SheetDefinition(
            name=title[:31],
            columns=headers,
            rows=[[str(cell) if cell is not None else "" for cell in row] for row in rows],
        )

    def _consolidate_tables(
        self, tables: list[tuple[str, dict]]
    ) -> SheetDefinition:
        """Consolidate multiple similar tables into one sheet with a category column."""
        if not tables:
            return SheetDefinition(name="Data")

        # Use first table's structure as base
        first_title, first_data = tables[0]
        base_headers = ["Category"] + list(first_data.get("headers", []))

        consolidated_rows: list[list[str]] = []
        for title, table_data in tables:
            category = title[:30]  # Truncate for display
            for row in table_data.get("rows", []):
                consolidated_rows.append([category] + [
                    str(cell) if cell is not None else "" for cell in row
                ])

        return SheetDefinition(
            name="Consolidated Data",
            columns=base_headers,
            rows=consolidated_rows,
        )

    def _document_to_json(self, document: ParsedDocument) -> dict:
        """Convert ParsedDocument to JSON-serializable dict for LLM prompt."""
        sections_json = []
        for section in document.sections:
            blocks_json = []
            for block in section.content:
                block_data = {
                    "type": block.content_type.value,
                    "data": block.data,
                }
                blocks_json.append(block_data)

            sections_json.append({
                "title": section.title,
                "level": section.level,
                "content": blocks_json,
            })

        return {
            "title": document.title,
            "sections": sections_json,
        }

    @staticmethod
    def _default_prompt() -> str:
        """Default prompt template for LLM reorganization."""
        return """You are a data organization expert. Analyze the following document structure
and reorganize it into logical Excel tables suitable for business analysis.

INPUT: A document with sections, tables, and lists.
OUTPUT: A structured plan for Excel sheets with clear table definitions.

Rules:
1. CONSOLIDATE related metrics into coherent tables (don't create a sheet per section)
2. CREATE a "Dashboard" sheet with key KPIs if quantitative data exists
3. FLATTEN hierarchical sections into table rows where appropriate
4. PRESERVE table structure where it already exists
5. GROUP similar data types (e.g., all regional data in one sheet)

For each sheet, specify:
- name: Short, descriptive sheet name (max 31 chars)
- type: One of: dashboard | breakdown | timeline | comparison | matrix | raw
- columns: List of column headers
- rows: List of row data (each row is a list of cell values)
- description: Brief explanation of what this sheet contains

Return ONLY valid JSON in this exact format:
{{
  "sheets": [
    {{
      "name": "Dashboard",
      "type": "dashboard",
      "columns": ["Metric", "Value", "Change"],
      "rows": [["Revenue", "$12.4M", "+28%"]],
      "description": "Key performance indicators summary"
    }}
  ],
  "consolidation_notes": "Brief notes on what was consolidated"
}}

Document structure to analyze:
---
{document_json}
---
"""


# ---------------------------------------------------------------------------
# Factory function for easy integration
# ---------------------------------------------------------------------------

def create_reorganizer(
    provider: Any | None = None,
    config_path: Path | None = None,
) -> SpreadsheetReorganizer:
    """
    Factory function to create a configured SpreadsheetReorganizer.

    Args:
        provider: LLMProvider instance (optional)
        config_path: Explicit YAML config path (optional). When omitted,
            resolution is delegated to ``config_loader.load_config()``, which
            finds the repo-local config during development and the bundled
            package config when installed.

    Returns:
        Configured SpreadsheetReorganizer instance.
    """
    from src.core.config_loader import load_config

    full_config = load_config(config_path)
    config = full_config.get("spreadsheet_reorganizer", {})

    return SpreadsheetReorganizer(provider=provider, config=config)
