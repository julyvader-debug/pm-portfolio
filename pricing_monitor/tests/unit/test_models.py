import pytest
from pydantic import ValidationError

from models import CompetitorProduct, ExtractionResult, AnalysisReport


# ---------------------------------------------------------------------------
# CompetitorProduct
# ---------------------------------------------------------------------------

class TestCompetitorProduct:
    def _valid(self, **overrides) -> dict:
        base = dict(
            competitor_name="Chewy",
            competitor_slug="chewy",
            canonical_name="NexGard 10-24lbs 6-pack",
            slug="nexgard-10-24lb-6pk",
            url="https://www.chewy.com/nexgard/dp/52063",
            category="flea_tick_oral",
            expected_price_range=(150.0, 200.0),
        )
        base.update(overrides)
        return base

    def test_valid_product_creates_successfully(self):
        p = CompetitorProduct(**self._valid())
        assert p.competitor_slug == "chewy"
        assert p.expected_price_range == (150.0, 200.0)

    def test_defaults_applied(self):
        p = CompetitorProduct(**self._valid())
        assert p.rate_limit_delay_seconds == 3.0
        assert p.viewport == {"width": 1280, "height": 900}

    def test_custom_viewport_and_delay(self):
        p = CompetitorProduct(**self._valid(
            rate_limit_delay_seconds=5.0,
            viewport={"width": 1920, "height": 1080},
        ))
        assert p.rate_limit_delay_seconds == 5.0
        assert p.viewport["width"] == 1920

    def test_price_range_low_equals_high_raises(self):
        with pytest.raises(ValidationError, match="less than high"):
            CompetitorProduct(**self._valid(expected_price_range=(100.0, 100.0)))

    def test_price_range_low_greater_than_high_raises(self):
        with pytest.raises(ValidationError, match="less than high"):
            CompetitorProduct(**self._valid(expected_price_range=(200.0, 100.0)))

    def test_missing_required_field_raises(self):
        data = self._valid()
        del data["url"]
        with pytest.raises(ValidationError):
            CompetitorProduct(**data)


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------

class TestExtractionResult:
    def _valid(self, **overrides) -> dict:
        base = dict(
            run_date="2026-04-14",
            competitor_slug="chewy",
            product_slug="nexgard-10-24lb-6pk",
            canonical_name="NexGard 10-24lbs 6-pack",
            status="success",
        )
        base.update(overrides)
        return base

    def test_success_result_with_prices(self):
        r = ExtractionResult(**self._valid(
            price_standard=179.99,
            price_subscription=161.99,
            price_per_month=27.0,
            in_stock=True,
            confidence="high",
        ))
        assert r.status == "success"
        assert r.price_standard == 179.99
        assert r.confidence == "high"

    def test_scrape_failed_result(self):
        r = ExtractionResult(**self._valid(
            status="scrape_failed",
            error="timeout after 5000ms",
        ))
        assert r.status == "scrape_failed"
        assert r.price_standard is None
        assert r.error == "timeout after 5000ms"

    def test_extraction_failed_result(self):
        r = ExtractionResult(**self._valid(
            status="extraction_failed",
            error="page_blocked",
        ))
        assert r.status == "extraction_failed"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            ExtractionResult(**self._valid(status="unknown_status"))

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            ExtractionResult(**self._valid(confidence="very_high"))

    def test_optional_fields_default_to_none(self):
        r = ExtractionResult(**self._valid())
        assert r.price_standard is None
        assert r.price_sale is None
        assert r.price_subscription is None
        assert r.price_per_month is None
        assert r.in_stock is None
        assert r.confidence is None
        assert r.error is None

    # best_price property
    def test_best_price_prefers_subscription(self):
        r = ExtractionResult(**self._valid(
            price_standard=180.0,
            price_sale=170.0,
            price_subscription=160.0,
        ))
        assert r.best_price == 160.0

    def test_best_price_falls_back_to_sale(self):
        r = ExtractionResult(**self._valid(
            price_standard=180.0,
            price_sale=170.0,
        ))
        assert r.best_price == 170.0

    def test_best_price_falls_back_to_standard(self):
        r = ExtractionResult(**self._valid(price_standard=180.0))
        assert r.best_price == 180.0

    def test_best_price_none_when_no_prices(self):
        r = ExtractionResult(**self._valid())
        assert r.best_price is None

    # is_price_in_range
    def test_price_in_range_returns_true(self):
        r = ExtractionResult(**self._valid(price_standard=175.0))
        assert r.is_price_in_range((150.0, 200.0)) is True

    def test_price_below_range_returns_false(self):
        r = ExtractionResult(**self._valid(price_standard=100.0))
        assert r.is_price_in_range((150.0, 200.0)) is False

    def test_price_above_range_returns_false(self):
        r = ExtractionResult(**self._valid(price_standard=250.0))
        assert r.is_price_in_range((150.0, 200.0)) is False

    def test_no_price_is_always_in_range(self):
        r = ExtractionResult(**self._valid())
        assert r.is_price_in_range((150.0, 200.0)) is True


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------

class TestAnalysisReport:
    def _make_result(self, status="success") -> ExtractionResult:
        return ExtractionResult(
            run_date="2026-04-14",
            competitor_slug="chewy",
            product_slug="nexgard-10-24lb-6pk",
            canonical_name="NexGard 10-24lbs 6-pack",
            status=status,
        )

    def test_valid_report(self):
        report = AnalysisReport(
            run_date="2026-04-14",
            markdown="# Report\n...",
            csv_rows=[{"competitor": "chewy", "price": 179.99}],
            extraction_results=[self._make_result()],
        )
        assert report.run_date == "2026-04-14"
        assert len(report.csv_rows) == 1

    def test_success_count(self):
        results = [
            self._make_result("success"),
            self._make_result("success"),
            self._make_result("scrape_failed"),
        ]
        report = AnalysisReport(
            run_date="2026-04-14",
            markdown="",
            csv_rows=[],
            extraction_results=results,
        )
        assert report.success_count == 2
        assert report.failure_count == 1

    def test_all_failures(self):
        results = [
            self._make_result("scrape_failed"),
            self._make_result("extraction_failed"),
        ]
        report = AnalysisReport(
            run_date="2026-04-14",
            markdown="",
            csv_rows=[],
            extraction_results=results,
        )
        assert report.success_count == 0
        assert report.failure_count == 2

    def test_empty_results(self):
        report = AnalysisReport(
            run_date="2026-04-14",
            markdown="",
            csv_rows=[],
            extraction_results=[],
        )
        assert report.success_count == 0
        assert report.failure_count == 0
