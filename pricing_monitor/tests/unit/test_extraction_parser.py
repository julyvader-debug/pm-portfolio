import json
import pytest

from extraction.parser import parse_haiku_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(raw: dict | str, expected_range=(150.0, 200.0)) -> object:
    if isinstance(raw, dict):
        raw = json.dumps(raw)
    return parse_haiku_response(
        raw_json=raw,
        run_date="2026-04-14",
        competitor_slug="chewy",
        product_slug="nexgard-10-24lb-6pk",
        canonical_name="NexGard 10-24lbs 6-pack",
        expected_price_range=expected_range,
    )


GOOD_RESPONSE = {
    "price_standard": 179.99,
    "price_sale": None,
    "price_subscription": 161.99,
    "price_per_month_usd": 27.0,
    "unit_size": "6-pack",
    "supply_duration_weeks": 24,
    "in_stock": True,
    "confidence": "high",
    "error": None,
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_success_status(self):
        r = _parse(GOOD_RESPONSE)
        assert r.status == "success"

    def test_prices_parsed(self):
        r = _parse(GOOD_RESPONSE)
        assert r.price_standard == 179.99
        assert r.price_subscription == 161.99
        assert r.price_per_month == 27.0

    def test_metadata_fields(self):
        r = _parse(GOOD_RESPONSE)
        assert r.unit_size == "6-pack"
        assert r.supply_duration_weeks == 24
        assert r.in_stock is True

    def test_confidence_preserved(self):
        r = _parse(GOOD_RESPONSE)
        assert r.confidence == "high"

    def test_null_optional_prices_allowed(self):
        data = {**GOOD_RESPONSE, "price_sale": None, "price_subscription": None}
        r = _parse(data)
        assert r.status == "success"
        assert r.price_sale is None
        assert r.price_subscription is None

    def test_result_identifiers_set(self):
        r = _parse(GOOD_RESPONSE)
        assert r.run_date == "2026-04-14"
        assert r.competitor_slug == "chewy"
        assert r.product_slug == "nexgard-10-24lb-6pk"
        assert r.canonical_name == "NexGard 10-24lbs 6-pack"


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------

class TestMalformedJson:
    def test_invalid_json_string(self):
        r = _parse("not json at all")
        assert r.status == "extraction_failed"
        assert "json_parse_error" in r.error

    def test_truncated_json(self):
        r = _parse('{"price_standard": 179.99')
        assert r.status == "extraction_failed"
        assert "json_parse_error" in r.error

    def test_json_array_not_object(self):
        r = _parse("[1, 2, 3]")
        assert r.status == "extraction_failed"
        assert r.error == "json_not_an_object"

    def test_empty_string(self):
        r = _parse("")
        assert r.status == "extraction_failed"

    def test_null_json(self):
        r = _parse("null")
        assert r.status == "extraction_failed"


# ---------------------------------------------------------------------------
# Blocked / no-pricing pages
# ---------------------------------------------------------------------------

class TestBlockedPages:
    def test_page_blocked_error(self):
        r = _parse({**GOOD_RESPONSE, "error": "page_blocked", "price_standard": None, "confidence": "low"})
        assert r.status == "extraction_failed"
        assert r.error == "page_blocked"

    def test_login_required_error(self):
        r = _parse({**GOOD_RESPONSE, "error": "login_required", "price_standard": None, "confidence": "low"})
        assert r.status == "extraction_failed"

    def test_captcha_error(self):
        r = _parse({**GOOD_RESPONSE, "error": "captcha", "price_standard": None, "confidence": "low"})
        assert r.status == "extraction_failed"

    def test_no_pricing_error(self):
        r = _parse({**GOOD_RESPONSE, "error": "no_pricing", "price_standard": None, "confidence": "low"})
        assert r.status == "extraction_failed"

    def test_unknown_error_string_does_not_fail(self):
        # A non-blocked error string should not trigger extraction_failed on its own
        r = _parse({**GOOD_RESPONSE, "error": "minor_warning"})
        assert r.status == "success"


# ---------------------------------------------------------------------------
# Missing confidence field
# ---------------------------------------------------------------------------

class TestMissingConfidence:
    def test_missing_confidence_is_extraction_failed(self):
        data = {k: v for k, v in GOOD_RESPONSE.items() if k != "confidence"}
        r = _parse(data)
        assert r.status == "extraction_failed"
        assert r.error == "missing_confidence"

    def test_invalid_confidence_value(self):
        r = _parse({**GOOD_RESPONSE, "confidence": "very_high"})
        assert r.status == "extraction_failed"


# ---------------------------------------------------------------------------
# Price sanity check — out-of-range forces confidence to low
# ---------------------------------------------------------------------------

class TestPriceSanityCheck:
    def test_price_within_range_keeps_confidence(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": 175.0, "price_subscription": None}, expected_range=(150, 200))
        assert r.status == "success"
        assert r.confidence == "high"

    def test_price_below_range_forces_low_confidence(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": 50.0, "price_subscription": None}, expected_range=(150, 200))
        assert r.status == "success"
        assert r.confidence == "low"

    def test_price_above_range_forces_low_confidence(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": 300.0, "price_subscription": None}, expected_range=(150, 200))
        assert r.status == "success"
        assert r.confidence == "low"

    def test_subscription_price_used_for_range_check(self):
        # subscription is best_price — if it's in range, confidence stays
        r = _parse({**GOOD_RESPONSE, "price_standard": 300.0, "price_subscription": 160.0}, expected_range=(150, 200))
        assert r.confidence == "high"

    def test_no_price_does_not_affect_confidence(self):
        data = {**GOOD_RESPONSE, "price_standard": None, "price_sale": None, "price_subscription": None}
        r = _parse(data)
        assert r.status == "success"
        assert r.confidence == "high"


# ---------------------------------------------------------------------------
# Invalid field values
# ---------------------------------------------------------------------------

class TestInvalidFields:
    def test_non_numeric_price_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": "free"})
        assert r.status == "extraction_failed"

    def test_negative_price_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": -5.0})
        assert r.status == "extraction_failed"

    def test_price_over_ceiling_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "price_standard": 99999.0})
        assert r.status == "extraction_failed"

    def test_non_bool_in_stock_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "in_stock": "yes"})
        assert r.status == "extraction_failed"

    def test_integer_in_stock_coerced_to_bool(self):
        r = _parse({**GOOD_RESPONSE, "in_stock": 1})
        assert r.status == "success"
        assert r.in_stock is True

    def test_non_string_unit_size_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "unit_size": 6})
        assert r.status == "extraction_failed"

    def test_non_int_supply_weeks_is_extraction_failed(self):
        r = _parse({**GOOD_RESPONSE, "supply_duration_weeks": "twenty-four"})
        assert r.status == "extraction_failed"
