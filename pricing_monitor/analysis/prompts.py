"""Prompt templates for Sonnet analysis."""
from __future__ import annotations

import json
from models import ExtractionResult

SYSTEM_PROMPT = """You are a pricing analyst for a veterinary product distributor.

You will receive:
1. A JSON object containing the current week's price extraction results across competitors.
2. A JSON object containing up to 8 weeks of historical price observations for the same products.

Your task is to produce a structured pricing report in this exact format:

---

## Executive Summary
2-4 sentences summarizing the most important pricing insights this week.

## Product Comparison
A markdown table comparing current prices across competitors for each product.
Columns: Product | Competitor | Standard Price | Sale Price | Subscription Price | In Stock | Confidence

## Price Trend Analysis
For each product, describe price movement over the available history (up / down / stable).
Include specific dollar amounts and percentage changes where available.

## Notable Findings
Bullet list of the most actionable observations (price gaps, out-of-stock items,
confidence issues, significant changes vs. prior week).

## Data Quality Notes
Note any extractions with low confidence, failed scrapes, or missing data.

---

After the markdown report, append a CSV data block in this exact format:

<CSV_DATA>
[
  {
    "run_date": "YYYY-MM-DD",
    "competitor_slug": "...",
    "product_slug": "...",
    "canonical_name": "...",
    "category": "...",
    "price_standard": <number or null>,
    "price_sale": <number or null>,
    "price_subscription": <number or null>,
    "price_per_month": <number or null>,
    "vs_previous_price": <number or null>,
    "in_stock": <true/false/null>,
    "unit_size": <string or null>,
    "supply_duration_weeks": <integer or null>,
    "confidence": "high" | "medium" | "low" | null,
    "scrape_status": "success" | "scrape_failed" | "extraction_failed"
  },
  ...
]
</CSV_DATA>

Rules:
- vs_previous_price: difference between current best price and the most recent prior week's best price. Null if no prior data.
- Include one row per product+competitor combination, including failures.
- Do not include any text after the closing </CSV_DATA> tag."""


def build_history_block(history_by_product: dict[str, list[dict]]) -> str:
    """Serialize historical DB rows as a JSON string for the cached history block."""
    return json.dumps(
        {"history": history_by_product},
        indent=2,
        default=str,
    )


def build_current_run_block(
    run_date: str,
    results: list[ExtractionResult],
) -> str:
    """Serialize the current run's extraction results as a JSON string."""
    return json.dumps(
        {
            "run_date": run_date,
            "results": [r.model_dump() for r in results],
        },
        indent=2,
        default=str,
    )
