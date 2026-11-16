from __future__ import annotations

import json
import re

from anthropic import AsyncAnthropic

from models import AnalysisReport, ExtractionResult
from analysis.prompts import (
    SYSTEM_PROMPT,
    build_current_run_block,
    build_history_block,
)

_CSV_DATA_RE = re.compile(r"<CSV_DATA>\s*(.*?)\s*</CSV_DATA>", re.DOTALL)


async def analyze_run(
    run_date: str,
    extraction_results: list[ExtractionResult],
    history_by_product: dict[str, list[dict]],
    client: AsyncAnthropic,
    model: str = "claude-sonnet-4-6",
) -> AnalysisReport:
    """
    Send current extraction results + history to Sonnet and return an AnalysisReport.

    The history block uses prompt caching (cache_control) to reduce cost on
    repeated calls with the same historical data.
    """
    history_text = build_history_block(history_by_product)
    current_text = build_current_run_block(run_date, extraction_results)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Historical price data (up to 8 weeks):\n\n{history_text}",
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"Current run results:\n\n{current_text}",
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        # Return a minimal report so the run doesn't abort entirely
        return AnalysisReport(
            run_date=run_date,
            markdown=f"## Analysis Error\n\nSonnet API call failed: {exc}",
            csv_rows=[],
            extraction_results=extraction_results,
        )

    raw_text = response.content[0].text
    markdown, csv_rows = _parse_response(raw_text)

    return AnalysisReport(
        run_date=run_date,
        markdown=markdown,
        csv_rows=csv_rows,
        extraction_results=extraction_results,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_response(raw_text: str) -> tuple[str, list[dict]]:
    """
    Split Sonnet's response into (markdown, csv_rows).

    If the <CSV_DATA> block is missing or contains invalid JSON,
    returns empty csv_rows rather than raising.
    """
    match = _CSV_DATA_RE.search(raw_text)

    if not match:
        # Strip any partial tag remnants and return what we have
        markdown = raw_text.strip()
        return markdown, []

    csv_json = match.group(1).strip()
    # Markdown is everything before the <CSV_DATA> tag
    markdown = raw_text[: match.start()].strip()

    try:
        csv_rows = json.loads(csv_json)
        if not isinstance(csv_rows, list):
            csv_rows = []
    except (json.JSONDecodeError, ValueError):
        csv_rows = []

    return markdown, csv_rows
