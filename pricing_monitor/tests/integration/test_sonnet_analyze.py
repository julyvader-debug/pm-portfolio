"""
Integration tests for sonnet_analyze.py.

Anthropic client is mocked at the SDK boundary — no real API calls are made.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from models import ExtractionResult, AnalysisReport
from analysis.sonnet_analyze import analyze_run, _parse_response


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

RUN_DATE = "2026-04-14"

SAMPLE_MARKDOWN = """## Executive Summary
Chewy holds the lowest subscription price this week at $161.99 for NexGard.

## Product Comparison
| Product | Competitor | Standard Price | Subscription Price | In Stock |
|---------|-----------|---------------|-------------------|----------|
| NexGard 10-24lbs 6-pack | chewy | $179.99 | $161.99 | Yes |
| NexGard 10-24lbs 6-pack | petmeds | $182.50 | N/A | Yes |

## Price Trend Analysis
NexGard prices stable week-over-week across all competitors.

## Notable Findings
- Chewy subscription saves $18/unit vs. standard price.

## Data Quality Notes
All extractions returned high confidence this week."""

SAMPLE_CSV_ROWS = [
    {
        "run_date": "2026-04-14",
        "competitor_slug": "chewy",
        "product_slug": "nexgard-10-24lb-6pk",
        "canonical_name": "NexGard 10-24lbs 6-pack",
        "category": "flea_tick_oral",
        "price_standard": 179.99,
        "price_sale": None,
        "price_subscription": 161.99,
        "price_per_month": 27.0,
        "vs_previous_price": -2.00,
        "in_stock": True,
        "unit_size": "6-pack",
        "supply_duration_weeks": 24,
        "confidence": "high",
        "scrape_status": "success",
    }
]

FULL_RESPONSE = f"{SAMPLE_MARKDOWN}\n\n<CSV_DATA>\n{json.dumps(SAMPLE_CSV_ROWS, indent=2)}\n</CSV_DATA>"


def _make_result(status="success", competitor_slug="chewy") -> ExtractionResult:
    return ExtractionResult(
        run_date=RUN_DATE,
        competitor_slug=competitor_slug,
        product_slug="nexgard-10-24lb-6pk",
        canonical_name="NexGard 10-24lbs 6-pack",
        status=status,
        price_standard=179.99 if status == "success" else None,
        price_subscription=161.99 if status == "success" else None,
        confidence="high" if status == "success" else None,
        error=None if status == "success" else "scrape_timeout",
    )


def _mock_client(response_text: str) -> AsyncMock:
    text_block = MagicMock()
    text_block.text = response_text
    message = MagicMock()
    message.content = [text_block]
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=message)
    return client


SAMPLE_HISTORY = {
    "nexgard-10-24lb-6pk": [
        {
            "run_date": "2026-04-07",
            "competitor_slug": "chewy",
            "price_standard": 181.99,
            "price_subscription": 163.99,
            "scrape_status": "success",
        }
    ]
}


# ---------------------------------------------------------------------------
# _parse_response unit tests (pure function — no mock needed)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_splits_markdown_and_csv(self):
        md, rows = _parse_response(FULL_RESPONSE)
        assert "## Executive Summary" in md
        assert "<CSV_DATA>" not in md
        assert len(rows) == 1

    def test_csv_values_correct(self):
        _, rows = _parse_response(FULL_RESPONSE)
        assert rows[0]["competitor_slug"] == "chewy"
        assert rows[0]["vs_previous_price"] == -2.00

    def test_missing_csv_block_returns_empty_list(self):
        md, rows = _parse_response(SAMPLE_MARKDOWN)
        assert rows == []
        assert "## Executive Summary" in md

    def test_invalid_json_in_csv_block_returns_empty_list(self):
        bad = f"{SAMPLE_MARKDOWN}\n\n<CSV_DATA>\nnot valid json\n</CSV_DATA>"
        _, rows = _parse_response(bad)
        assert rows == []

    def test_csv_block_containing_object_not_list_returns_empty(self):
        bad = f"{SAMPLE_MARKDOWN}\n\n<CSV_DATA>\n{{\"key\": \"value\"}}\n</CSV_DATA>"
        _, rows = _parse_response(bad)
        assert rows == []

    def test_markdown_trimmed_of_whitespace(self):
        padded = f"  \n\n{SAMPLE_MARKDOWN}\n\n<CSV_DATA>[]\n</CSV_DATA>\n\n  "
        md, _ = _parse_response(padded)
        assert not md.startswith(" ")
        assert not md.endswith(" ")

    def test_empty_csv_block_returns_empty_list(self):
        response = f"{SAMPLE_MARKDOWN}\n\n<CSV_DATA>[]\n</CSV_DATA>"
        _, rows = _parse_response(response)
        assert rows == []


# ---------------------------------------------------------------------------
# analyze_run integration tests (mocked client)
# ---------------------------------------------------------------------------

class TestAnalyzeRun:
    async def test_returns_analysis_report(self):
        client = _mock_client(FULL_RESPONSE)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert isinstance(report, AnalysisReport)

    async def test_run_date_set(self):
        client = _mock_client(FULL_RESPONSE)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert report.run_date == RUN_DATE

    async def test_markdown_contains_required_sections(self):
        from storage.export import REQUIRED_MD_SECTIONS
        client = _mock_client(FULL_RESPONSE)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        for section in REQUIRED_MD_SECTIONS:
            assert section in report.markdown, f"Missing section: {section}"

    async def test_csv_rows_populated(self):
        client = _mock_client(FULL_RESPONSE)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert len(report.csv_rows) == 1
        assert report.csv_rows[0]["competitor_slug"] == "chewy"

    async def test_extraction_results_preserved(self):
        client = _mock_client(FULL_RESPONSE)
        results = [_make_result("success"), _make_result("scrape_failed", "petmeds")]
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=results,
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert report.extraction_results == results

    async def test_correct_model_called(self):
        client = _mock_client(FULL_RESPONSE)
        await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
            model="claude-sonnet-4-6",
        )
        _, kwargs = client.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-4-6"

    async def test_cache_control_on_system_and_history(self):
        """Both the system prompt and history block must have cache_control set."""
        client = _mock_client(FULL_RESPONSE)
        await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        _, kwargs = client.messages.create.call_args

        # System prompt cache_control
        system = kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

        # History block cache_control
        user_content = kwargs["messages"][0]["content"]
        history_block = user_content[0]
        assert history_block["cache_control"] == {"type": "ephemeral"}

        # Current run block has no cache_control
        current_block = user_content[1]
        assert "cache_control" not in current_block

    async def test_missing_csv_block_does_not_abort(self):
        """If Sonnet forgets the CSV_DATA block, report still returns with empty csv_rows."""
        client = _mock_client(SAMPLE_MARKDOWN)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert report.csv_rows == []
        assert "## Executive Summary" in report.markdown

    async def test_api_error_returns_minimal_report(self):
        """Sonnet API failure returns a report with an error message, not an exception."""
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("rate limit exceeded"))
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert report.run_date == RUN_DATE
        assert "rate limit exceeded" in report.markdown
        assert report.csv_rows == []

    async def test_partial_failures_included_in_results(self):
        """Mixed success/failure results are all passed through to the report."""
        client = _mock_client(FULL_RESPONSE)
        results = [
            _make_result("success", "chewy"),
            _make_result("scrape_failed", "petmeds"),
            _make_result("extraction_failed", "own_storefront"),
        ]
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=results,
            history_by_product=SAMPLE_HISTORY,
            client=client,
        )
        assert report.success_count == 1
        assert report.failure_count == 2

    async def test_empty_history_still_works(self):
        client = _mock_client(FULL_RESPONSE)
        report = await analyze_run(
            run_date=RUN_DATE,
            extraction_results=[_make_result()],
            history_by_product={},
            client=client,
        )
        assert isinstance(report, AnalysisReport)
