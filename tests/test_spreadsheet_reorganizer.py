"""
Tests for SpreadsheetReorganizer — rule-based consolidation (mechanical path)
and LLM-powered reorganization (mocked provider).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.core.models import (
    ContentBlock,
    ContentType,
    DocumentSection,
    ParsedDocument,
)
from src.core.planner.spreadsheet_reorganizer import (
    SpreadsheetReorganizer,
    create_reorganizer,
)


def doc(*sections: DocumentSection) -> ParsedDocument:
    return ParsedDocument(
        title="Report",
        source_path=Path("report.md"),
        source_format="markdown",
        sections=list(sections),
    )


def para(text: str) -> ContentBlock:
    return ContentBlock(content_type=ContentType.PARAGRAPH, data=text)


def lst(items: list[str]) -> ContentBlock:
    return ContentBlock(content_type=ContentType.LIST, data=items)


def table(headers: list[str], rows: list[list]) -> ContentBlock:
    return ContentBlock(content_type=ContentType.TABLE, data={"headers": headers, "rows": rows})


# ---------------------------------------------------------------------------
# reorganize() dispatch — enabled/disabled, provider present/absent, fallback
# ---------------------------------------------------------------------------

def test_disabled_uses_rule_based_mapping():
    reorganizer = SpreadsheetReorganizer(provider=MagicMock(), config={"enabled": False})
    document = doc(DocumentSection(title="Notes", level=1, content=[lst(["a", "b"])]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].name == "Notes"


def test_no_provider_uses_rule_based_mapping():
    reorganizer = SpreadsheetReorganizer(provider=None, config={"enabled": True})
    document = doc(DocumentSection(title="Notes", level=1, content=[lst(["a", "b"])]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].columns == ["Item"]


def test_llm_failure_falls_back_to_rule_based():
    provider = MagicMock()
    provider.generate.side_effect = RuntimeError("LLM unavailable")
    reorganizer = SpreadsheetReorganizer(provider=provider, config={"enabled": True})
    document = doc(DocumentSection(title="Notes", level=1, content=[lst(["a", "b"])]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].name == "Notes"


def test_llm_bad_json_falls_back_to_rule_based():
    provider = MagicMock()
    provider.generate.return_value = "not json"
    reorganizer = SpreadsheetReorganizer(provider=provider, config={"enabled": True})
    document = doc(DocumentSection(title="Notes", level=1, content=[lst(["a", "b"])]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].name == "Notes"


def test_llm_reorganize_converts_response_to_sheets():
    provider = MagicMock()
    provider.generate.return_value = (
        '{"sheets": [{"name": "Dashboard", "type": "dashboard", '
        '"columns": ["Metric", "Value"], "rows": [["Revenue", "$12.4M"]], '
        '"description": "KPIs"}], "consolidation_notes": "merged exec summary"}'
    )
    reorganizer = SpreadsheetReorganizer(provider=provider, config={"enabled": True, "max_sheets": 10})
    document = doc(DocumentSection(title="Executive Summary", level=1, content=[para("Revenue: $12.4M (+28%)")]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].name == "Dashboard"
    assert plan.sheets[0].columns == ["Metric", "Value"]
    assert plan.sheets[0].rows == [["Revenue", "$12.4M"]]
    provider.generate.assert_called_once()


def test_llm_reorganize_handles_markdown_fenced_response():
    """Real models (e.g. qwen2.5vl via Ollama) commonly wrap JSON replies in
    ```json ... ``` fences — the parser must extract the object, not choke on it."""
    provider = MagicMock()
    provider.generate.return_value = (
        "```json\n"
        '{"sheets": [{"name": "Dashboard", "type": "dashboard", '
        '"columns": ["Metric", "Value"], "rows": [["Revenue", "$12.4M"]], '
        '"description": "KPIs"}], "consolidation_notes": "merged exec summary"}'
        "\n```"
    )
    reorganizer = SpreadsheetReorganizer(provider=provider, config={"enabled": True, "max_sheets": 10})
    document = doc(DocumentSection(title="Executive Summary", level=1, content=[para("Revenue: $12.4M (+28%)")]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 1
    assert plan.sheets[0].name == "Dashboard"
    assert plan.sheets[0].rows == [["Revenue", "$12.4M"]]


def test_default_prompt_formats_without_brace_collision():
    """The built-in prompt embeds a literal JSON example alongside the
    {document_json} placeholder — its braces must be escaped ({{ }}) so
    str.format() substitutes the placeholder without choking on the example."""
    template = SpreadsheetReorganizer._default_prompt()

    prompt = template.format(document_json='{"sections": []}')

    assert '{"sections": []}' in prompt
    assert "{document_json}" not in prompt
    assert '"sheets": [' in prompt  # literal JSON example survived unescaped


def test_llm_reorganize_respects_max_sheets():
    provider = MagicMock()
    sheets_json = ", ".join(
        f'{{"name": "Sheet{i}", "type": "raw", "columns": ["A"], "rows": [["x"]]}}'
        for i in range(5)
    )
    provider.generate.return_value = f'{{"sheets": [{sheets_json}]}}'
    reorganizer = SpreadsheetReorganizer(provider=provider, config={"enabled": True, "max_sheets": 2})
    document = doc(DocumentSection(title="S", level=1, content=[para("x")]))

    plan = reorganizer.reorganize(document)

    assert len(plan.sheets) == 2


# ---------------------------------------------------------------------------
# Rule-based reorganization — KPI extraction -> Dashboard sheet
# ---------------------------------------------------------------------------

def test_kpi_paragraphs_become_dashboard_sheet():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(
            title="Executive Summary",
            level=1,
            content=[para("Revenue: $12.4M (+28%)"), para("Headcount: 340")],
        )
    )

    plan = reorganizer.reorganize(document)

    dashboard = next(s for s in plan.sheets if s.name == "Dashboard")
    assert dashboard.columns == ["Metric", "Value"]
    assert ["Revenue", "$12.4M (+28%)"] in dashboard.rows
    assert ["Headcount", "340"] in dashboard.rows


def test_kpi_extraction_from_lists():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(
            title="Highlights",
            level=1,
            content=[lst(["Profit Margin: 18%", "Customer Count: 5,200"])],
        )
    )

    plan = reorganizer.reorganize(document)

    dashboard = next(s for s in plan.sheets if s.name == "Dashboard")
    names = [row[0] for row in dashboard.rows]
    assert "Profit Margin" in names
    assert "Customer Count" in names


def test_non_metric_paragraphs_do_not_create_dashboard():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(title="Intro", level=1, content=[para("This report covers Q3 performance.")])
    )

    plan = reorganizer.reorganize(document)

    assert all(sheet.name != "Dashboard" for sheet in plan.sheets)


# ---------------------------------------------------------------------------
# Rule-based reorganization — table consolidation
# ---------------------------------------------------------------------------

def test_single_table_becomes_dedicated_sheet():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(
            title="Regional Sales",
            level=1,
            content=[table(["Region", "Revenue"], [["EMEA", "$4M"], ["APAC", "$3M"]])],
        )
    )

    plan = reorganizer.reorganize(document)

    sheet = next(s for s in plan.sheets if s.name == "Regional Sales")
    assert sheet.columns == ["Region", "Revenue"]
    assert sheet.rows == [["EMEA", "$4M"], ["APAC", "$3M"]]


def test_similar_tables_are_consolidated_with_category_column():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(
            title="Regional Breakdown",
            level=1,
            content=[table(["Quarter", "Revenue"], [["Q1", "$1M"]])],
        ),
        DocumentSection(
            title="Product Breakdown",
            level=1,
            content=[table(["Quarter", "Revenue"], [["Q1", "$2M"]])],
        ),
    )

    plan = reorganizer.reorganize(document)

    consolidated = next(s for s in plan.sheets if s.name == "Consolidated Data")
    assert consolidated.columns == ["Category", "Quarter", "Revenue"]
    assert ["Regional Breakdown", "Q1", "$1M"] in consolidated.rows
    assert ["Product Breakdown", "Q1", "$2M"] in consolidated.rows


def test_dissimilar_tables_stay_as_separate_sheets():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(title="Sales", level=1, content=[table(["Region", "Revenue"], [["EMEA", "$1M"]])]),
        DocumentSection(
            title="Risks",
            level=1,
            content=[table(["Risk", "Impact", "Likelihood"], [["Outage", "High", "Low"]])],
        ),
    )

    plan = reorganizer.reorganize(document)

    names = {s.name for s in plan.sheets}
    assert "Sales" in names
    assert "Risks" in names
    assert "Consolidated Data" not in names


# ---------------------------------------------------------------------------
# Rule-based reorganization — lists / paragraphs as fallback sheets
# ---------------------------------------------------------------------------

def test_list_section_becomes_item_sheet():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(DocumentSection(title="Action Items", level=1, content=[lst(["Ship v2", "Fix bug"])]))

    plan = reorganizer.reorganize(document)

    sheet = next(s for s in plan.sheets if s.name == "Action Items")
    assert sheet.columns == ["Item"]
    assert sheet.rows == [["Ship v2"], ["Fix bug"]]


def test_paragraph_only_section_becomes_text_sheet():
    reorganizer = SpreadsheetReorganizer(provider=None)
    document = doc(
        DocumentSection(title="Notes", level=1, content=[para("General context about the quarter.")])
    )

    plan = reorganizer.reorganize(document)

    sheet = next(s for s in plan.sheets if s.name == "Notes")
    assert sheet.columns == ["Text"]
    assert sheet.rows == [["General context about the quarter."]]


def test_rule_based_respects_max_sheets():
    sections = [
        DocumentSection(title=f"Section {i}", level=1, content=[lst([f"item {i}"])])
        for i in range(5)
    ]
    reorganizer = SpreadsheetReorganizer(provider=None, config={"max_sheets": 2})

    plan = reorganizer.reorganize(doc(*sections))

    assert len(plan.sheets) == 2


# ---------------------------------------------------------------------------
# create_reorganizer — factory + config resolution
# ---------------------------------------------------------------------------

def test_create_reorganizer_loads_spreadsheet_section_from_config(tmp_path):
    config_file = tmp_path / "rules.yaml"
    config_file.write_text(
        "spreadsheet_reorganizer:\n"
        "  enabled: false\n"
        "  max_sheets: 3\n",
        encoding="utf-8",
    )

    reorganizer = create_reorganizer(provider=None, config_path=config_file)

    assert reorganizer._enabled is False
    assert reorganizer._max_sheets == 3


def test_create_reorganizer_resolves_default_config_without_explicit_path():
    """The bug fix: no hardcoded relative path — config_loader finds the real default."""
    reorganizer = create_reorganizer(provider=None)

    # default_rules.yaml ships spreadsheet_reorganizer.enabled: true, max_sheets: 10
    assert reorganizer._enabled is True
    assert reorganizer._max_sheets == 10
