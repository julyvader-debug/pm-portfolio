import csv
import json
import pytest
from pathlib import Path

from storage.export import (
    write_markdown_report,
    write_csv,
    write_failures_json,
    write_all,
    CSV_COLUMNS,
    REQUIRED_MD_SECTIONS,
)
from models import AnalysisReport, ExtractionResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_MARKDOWN = "\n".join([
    "# Pricing Report — 2026-04-14",
    "",
    "## Executive Summary",
    "Three competitors tracked this week.",
    "",
    "## Product Comparison",
    "| Product | Chewy | PetMeds |",
    "|---------|-------|---------|",
    "| NexGard | $179 | $182 |",
    "",
    "## Price Trend Analysis",
    "Prices stable week-over-week.",
    "",
    "## Notable Findings",
    "Chewy subscription price dropped 5%.",
    "",
    "## Data Quality Notes",
    "All extractions returned high confidence.",
])

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
        "vs_previous_price": -5.00,
        "in_stock": True,
        "unit_size": "6-pack",
        "supply_duration_weeks": 24,
        "confidence": "high",
        "scrape_status": "success",
    },
    {
        "run_date": "2026-04-14",
        "competitor_slug": "petmeds",
        "product_slug": "nexgard-10-24lb-6pk",
        "canonical_name": "NexGard 10-24lbs 6-pack",
        "category": "flea_tick_oral",
        "price_standard": 182.50,
        "price_sale": None,
        "price_subscription": None,
        "price_per_month": None,
        "vs_previous_price": 0.0,
        "in_stock": True,
        "unit_size": "6-pack",
        "supply_duration_weeks": 24,
        "confidence": "high",
        "scrape_status": "success",
    },
]


def _make_result(status="success") -> ExtractionResult:
    return ExtractionResult(
        run_date="2026-04-14",
        competitor_slug="chewy",
        product_slug="nexgard-10-24lb-6pk",
        canonical_name="NexGard 10-24lbs 6-pack",
        status=status,
        price_standard=179.99 if status == "success" else None,
        confidence="high" if status == "success" else None,
        error=None if status == "success" else "scrape_timeout",
    )


def _make_report(**overrides) -> AnalysisReport:
    base = dict(
        run_date="2026-04-14",
        markdown=SAMPLE_MARKDOWN,
        csv_rows=SAMPLE_CSV_ROWS,
        extraction_results=[_make_result("success"), _make_result("scrape_failed")],
    )
    base.update(overrides)
    return AnalysisReport(**base)


# ---------------------------------------------------------------------------
# write_markdown_report
# ---------------------------------------------------------------------------

class TestWriteMarkdown:
    def test_file_created(self, tmp_path):
        path = write_markdown_report(tmp_path, SAMPLE_MARKDOWN)
        assert path.exists()
        assert path.name == "report.md"

    def test_content_preserved(self, tmp_path):
        write_markdown_report(tmp_path, SAMPLE_MARKDOWN)
        content = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert content == SAMPLE_MARKDOWN

    def test_all_required_sections_present(self, tmp_path):
        write_markdown_report(tmp_path, SAMPLE_MARKDOWN)
        content = (tmp_path / "report.md").read_text(encoding="utf-8")
        for section in REQUIRED_MD_SECTIONS:
            assert section in content, f"Missing section: {section}"

    def test_creates_run_dir_if_missing(self, tmp_path):
        run_dir = tmp_path / "2026-04-14"
        assert not run_dir.exists()
        write_markdown_report(run_dir, SAMPLE_MARKDOWN)
        assert run_dir.exists()

    def test_overwrites_existing_file(self, tmp_path):
        write_markdown_report(tmp_path, "old content")
        write_markdown_report(tmp_path, "new content")
        content = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert content == "new content"


# ---------------------------------------------------------------------------
# write_csv
# ---------------------------------------------------------------------------

class TestWriteCsv:
    def test_file_created(self, tmp_path):
        path = write_csv(tmp_path, SAMPLE_CSV_ROWS)
        assert path.exists()
        assert path.name == "report.csv"

    def test_header_contains_all_required_columns(self, tmp_path):
        write_csv(tmp_path, SAMPLE_CSV_ROWS)
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for col in CSV_COLUMNS:
                assert col in reader.fieldnames, f"Missing CSV column: {col}"

    def test_row_count_matches_input(self, tmp_path):
        write_csv(tmp_path, SAMPLE_CSV_ROWS)
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(SAMPLE_CSV_ROWS)

    def test_values_written_correctly(self, tmp_path):
        write_csv(tmp_path, SAMPLE_CSV_ROWS)
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["competitor_slug"] == "chewy"
        assert rows[0]["price_standard"] == "179.99"
        assert rows[0]["vs_previous_price"] == "-5.0"

    def test_none_values_written_as_empty_string(self, tmp_path):
        write_csv(tmp_path, SAMPLE_CSV_ROWS)
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["price_sale"] == ""

    def test_extra_keys_in_row_ignored(self, tmp_path):
        rows = [{**SAMPLE_CSV_ROWS[0], "unexpected_field": "surprise"}]
        path = write_csv(tmp_path, rows)
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "unexpected_field" not in reader.fieldnames

    def test_missing_keys_in_row_written_as_empty(self, tmp_path):
        minimal_row = {"run_date": "2026-04-14", "competitor_slug": "chewy"}
        write_csv(tmp_path, [minimal_row])
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["price_standard"] == ""

    def test_empty_rows_writes_header_only(self, tmp_path):
        write_csv(tmp_path, [])
        with (tmp_path / "report.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows == []

    def test_creates_run_dir_if_missing(self, tmp_path):
        run_dir = tmp_path / "2026-04-14"
        write_csv(run_dir, SAMPLE_CSV_ROWS)
        assert run_dir.exists()


# ---------------------------------------------------------------------------
# write_failures_json
# ---------------------------------------------------------------------------

class TestWriteFailuresJson:
    def test_file_created(self, tmp_path):
        path = write_failures_json(tmp_path, [_make_result("scrape_failed")])
        assert path.exists()
        assert path.name == "failures.json"

    def test_only_failures_included(self, tmp_path):
        results = [
            _make_result("success"),
            _make_result("scrape_failed"),
            _make_result("extraction_failed"),
        ]
        write_failures_json(tmp_path, results)
        data = json.loads((tmp_path / "failures.json").read_text(encoding="utf-8"))
        assert len(data) == 2
        statuses = {r["status"] for r in data}
        assert statuses == {"scrape_failed", "extraction_failed"}

    def test_valid_json_output(self, tmp_path):
        write_failures_json(tmp_path, [_make_result("scrape_failed")])
        raw = (tmp_path / "failures.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, list)

    def test_failure_fields_present(self, tmp_path):
        write_failures_json(tmp_path, [_make_result("scrape_failed")])
        data = json.loads((tmp_path / "failures.json").read_text(encoding="utf-8"))
        row = data[0]
        assert "competitor_slug" in row
        assert "product_slug" in row
        assert "status" in row
        assert "error" in row

    def test_no_failures_writes_empty_array(self, tmp_path):
        write_failures_json(tmp_path, [_make_result("success")])
        data = json.loads((tmp_path / "failures.json").read_text(encoding="utf-8"))
        assert data == []

    def test_empty_list_writes_empty_array(self, tmp_path):
        write_failures_json(tmp_path, [])
        data = json.loads((tmp_path / "failures.json").read_text(encoding="utf-8"))
        assert data == []

    def test_creates_run_dir_if_missing(self, tmp_path):
        run_dir = tmp_path / "2026-04-14"
        write_failures_json(run_dir, [])
        assert run_dir.exists()


# ---------------------------------------------------------------------------
# write_all
# ---------------------------------------------------------------------------

class TestWriteAll:
    def test_all_three_files_created(self, tmp_path):
        report = _make_report()
        paths = write_all(tmp_path, report)
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "report.csv").exists()
        assert (tmp_path / "failures.json").exists()
        assert set(paths.keys()) == {"markdown", "csv", "failures"}

    def test_returns_correct_paths(self, tmp_path):
        report = _make_report()
        paths = write_all(tmp_path, report)
        assert paths["markdown"] == tmp_path / "report.md"
        assert paths["csv"] == tmp_path / "report.csv"
        assert paths["failures"] == tmp_path / "failures.json"
