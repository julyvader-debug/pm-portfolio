from __future__ import annotations

import json
from typing import Any

from models import ExtractionResult, ExtractionConfidence

# Prices outside this absolute floor are always flagged regardless of config range
_ABSOLUTE_PRICE_FLOOR = 0.01
_ABSOLUTE_PRICE_CEILING = 10_000.0

# Known error strings Haiku returns when a page is blocked or has no pricing
_BLOCKED_ERRORS = {"page_blocked", "login_required", "captcha", "no_pricing"}


def parse_haiku_response(
    raw_json: str,
    run_date: str,
    competitor_slug: str,
    product_slug: str,
    canonical_name: str,
    expected_price_range: tuple[float, float],
    extracted_at: str | None = None,
) -> ExtractionResult:
    """
    Parse the JSON string returned by Haiku and return an ExtractionResult.

    On any parse/validation failure the result has status='extraction_failed'.
    Prices outside expected_price_range are accepted but confidence is forced to 'low'.
    """
    base = dict(
        run_date=run_date,
        competitor_slug=competitor_slug,
        product_slug=product_slug,
        canonical_name=canonical_name,
    )

    # --- Parse JSON ---
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return ExtractionResult(**base, status="extraction_failed", error=f"json_parse_error: {exc}")

    if not isinstance(data, dict):
        return ExtractionResult(**base, status="extraction_failed", error="json_not_an_object")

    # --- Blocked / no-pricing pages ---
    error_val = data.get("error")
    if error_val and str(error_val).lower() in _BLOCKED_ERRORS:
        return ExtractionResult(**base, status="extraction_failed", error=str(error_val))

    # --- Extract and coerce fields ---
    try:
        price_standard = _parse_price(data.get("price_standard"))
        price_sale = _parse_price(data.get("price_sale"))
        price_subscription = _parse_price(data.get("price_subscription"))
        price_per_month = _parse_price(data.get("price_per_month_usd"))
        in_stock = _parse_bool(data.get("in_stock"))
        unit_size = _parse_str(data.get("unit_size"))
        supply_duration_weeks = _parse_int(data.get("supply_duration_weeks"))
        confidence = _parse_confidence(data.get("confidence"))
    except _ParseError as exc:
        return ExtractionResult(**base, status="extraction_failed", error=str(exc))

    # confidence is required — treat missing as extraction_failed
    if confidence is None:
        return ExtractionResult(**base, status="extraction_failed", error="missing_confidence")

    # --- Sanity-check price against expected range ---
    best = _best_price(price_subscription, price_sale, price_standard)
    if best is not None and not _in_range(best, expected_price_range):
        confidence = "low"

    return ExtractionResult(
        **base,
        status="success",
        price_standard=price_standard,
        price_sale=price_sale,
        price_subscription=price_subscription,
        price_per_month=price_per_month,
        in_stock=in_stock,
        unit_size=unit_size,
        supply_duration_weeks=supply_duration_weeks,
        confidence=confidence,
        error=error_val if error_val else None,
        extracted_at=extracted_at,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _ParseError(Exception):
    pass


def _parse_price(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        raise _ParseError(f"invalid price value: {val!r}")
    if f < _ABSOLUTE_PRICE_FLOOR or f > _ABSOLUTE_PRICE_CEILING:
        raise _ParseError(f"price {f} outside absolute bounds")
    return f


def _parse_bool(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    raise _ParseError(f"invalid bool value: {val!r}")


def _parse_str(val: Any) -> str | None:
    if val is None:
        return None
    if not isinstance(val, str):
        raise _ParseError(f"expected string, got: {val!r}")
    return val.strip() or None


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        raise _ParseError(f"invalid int value: {val!r}")


def _parse_confidence(val: Any) -> ExtractionConfidence | None:
    if val is None:
        return None
    if val not in ("high", "medium", "low"):
        raise _ParseError(f"invalid confidence value: {val!r}")
    return val  # type: ignore[return-value]


def _best_price(
    subscription: float | None,
    sale: float | None,
    standard: float | None,
) -> float | None:
    return subscription or sale or standard


def _in_range(price: float, expected_range: tuple[float, float]) -> bool:
    low, high = expected_range
    return low <= price <= high
