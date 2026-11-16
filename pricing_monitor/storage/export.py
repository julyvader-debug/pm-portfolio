from __future__ import annotations

import csv
import json
from pathlib import Path

from models import AnalysisReport, ExtractionResult

# Required columns in every exported CSV — order is preserved in output
CSV_COLUMNS = [
    "run_date",
    "competitor_slug",
    "product_slug",
    "canonical_name",
    "category",
    "price_standard",
    "price_sale",
    "price_subscription",
    "price_per_month",
    "vs_previous_price",
    "in_stock",
    "unit_size",
    "supply_duration_weeks",
    "confidence",
    "scrape_status",
]

# Markdown sections every valid report must contain
REQUIRED_MD_SECTIONS = [
    "## Executive Summary",
    "## Product Comparison",
    "## Price Trend Analysis",
    "## Notable Findings",
    "## Data Quality Notes",
]


def write_markdown_report(run_dir: Path, markdown: str) -> Path:
    """Write report.md to run_dir. Returns the path written."""
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "report.md"
    out.write_text(markdown, encoding="utf-8")
    return out


def write_csv(run_dir: Path, csv_rows: list[dict]) -> Path:
    """
    Write report.csv to run_dir.

    Each row dict may contain a subset of CSV_COLUMNS; missing keys are written
    as empty strings. Extra keys are ignored. Returns the path written.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "report.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
            restval="",
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    return out


def write_failures_json(run_dir: Path, results: list[ExtractionResult]) -> Path:
    """
    Write failures.json containing all non-success ExtractionResults.
    Returns the path written (file is written even if there are no failures).
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "failures.json"
    failures = [
        r.model_dump()
        for r in results
        if r.status != "success"
    ]
    out.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    return out


def write_all(run_dir: Path, report: AnalysisReport) -> dict[str, Path]:
    """Convenience: write all three outputs and return a dict of paths."""
    return {
        "markdown": write_markdown_report(run_dir, report.markdown),
        "csv": write_csv(run_dir, report.csv_rows),
        "failures": write_failures_json(run_dir, report.extraction_results),
    }
