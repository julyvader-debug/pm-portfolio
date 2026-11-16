import pytest
from pathlib import Path

from storage.db import PriceDB
from models import ExtractionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> PriceDB:
    return PriceDB(tmp_path / "test.db")


def _result(
    run_date="2026-04-14",
    competitor_slug="chewy",
    product_slug="nexgard-10-24lb-6pk",
    canonical_name="NexGard 10-24lbs 6-pack",
    status="success",
    price_standard=179.99,
    **kwargs,
) -> ExtractionResult:
    if "confidence" not in kwargs:
        kwargs["confidence"] = "high" if status == "success" else None
    return ExtractionResult(
        run_date=run_date,
        competitor_slug=competitor_slug,
        product_slug=product_slug,
        canonical_name=canonical_name,
        status=status,
        price_standard=price_standard,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Schema / init
# ---------------------------------------------------------------------------

class TestInit:
    def test_db_file_created(self, tmp_path):
        db_path = tmp_path / "sub" / "pricing.db"
        PriceDB(db_path)
        assert db_path.exists()

    def test_parent_dirs_created(self, tmp_path):
        db_path = tmp_path / "a" / "b" / "c" / "pricing.db"
        PriceDB(db_path)
        assert db_path.exists()

    def test_second_init_does_not_error(self, tmp_path):
        db_path = tmp_path / "pricing.db"
        PriceDB(db_path)
        PriceDB(db_path)  # CREATE TABLE IF NOT EXISTS — should not raise


# ---------------------------------------------------------------------------
# Insert (append-only)
# ---------------------------------------------------------------------------

class TestInsert:
    def test_insert_success_row(self, db):
        db.insert(_result())
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert len(rows) == 1
        assert rows[0]["price_standard"] == 179.99

    def test_insert_failed_row_stored(self, db):
        db.insert(_result(status="scrape_failed", price_standard=None, confidence=None))
        # get_trend only returns successes, so use run dates to confirm it was stored
        dates = db.get_recent_run_dates()
        assert "2026-04-14" in dates

    def test_duplicate_run_date_both_stored(self, db):
        """Append-only: two rows for the same product+date are both kept."""
        db.insert(_result(run_date="2026-04-14", price_standard=179.99))
        db.insert(_result(run_date="2026-04-14", price_standard=175.00))
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert len(rows) == 2

    def test_insert_many(self, db):
        results = [
            _result(run_date="2026-04-07"),
            _result(run_date="2026-04-14"),
        ]
        db.insert_many(results)
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert len(rows) == 2

    def test_in_stock_stored_as_integer(self, db):
        db.insert(_result(in_stock=True))
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert rows[0]["in_stock"] == 1

    def test_none_prices_stored_as_null(self, db):
        db.insert(_result(price_sale=None, price_subscription=None))
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert rows[0]["price_sale"] is None
        assert rows[0]["price_subscription"] is None


# ---------------------------------------------------------------------------
# get_trend
# ---------------------------------------------------------------------------

class TestGetTrend:
    def test_returns_newest_first(self, db):
        for week in range(1, 5):
            db.insert(_result(run_date=f"2026-03-{week:02d}"))
        rows = db.get_trend("nexgard-10-24lb-6pk")
        dates = [r["run_date"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_limit_respected(self, db):
        for week in range(1, 12):
            db.insert(_result(run_date=f"2026-02-{week:02d}"))
        rows = db.get_trend("nexgard-10-24lb-6pk", weeks=8)
        assert len(rows) == 8

    def test_only_success_rows_returned(self, db):
        db.insert(_result(run_date="2026-04-14", status="success"))
        db.insert(_result(run_date="2026-04-13", status="scrape_failed", price_standard=None, confidence=None))
        db.insert(_result(run_date="2026-04-12", status="extraction_failed", price_standard=None, confidence=None))
        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert len(rows) == 1
        assert rows[0]["run_date"] == "2026-04-14"

    def test_different_products_isolated(self, db):
        db.insert(_result(product_slug="nexgard-10-24lb-6pk"))
        db.insert(_result(product_slug="frontline-plus-23-44lb-6pk"))
        nexgard = db.get_trend("nexgard-10-24lb-6pk")
        frontline = db.get_trend("frontline-plus-23-44lb-6pk")
        assert len(nexgard) == 1
        assert len(frontline) == 1

    def test_no_rows_returns_empty_list(self, db):
        rows = db.get_trend("nonexistent-product")
        assert rows == []

    def test_row_contains_expected_fields(self, db):
        db.insert(_result(
            price_standard=179.99,
            price_subscription=161.99,
            unit_size="6-pack",
            supply_duration_weeks=24,
        ))
        row = db.get_trend("nexgard-10-24lb-6pk")[0]
        assert row["competitor_slug"] == "chewy"
        assert row["canonical_name"] == "NexGard 10-24lbs 6-pack"
        assert row["price_subscription"] == 161.99
        assert row["unit_size"] == "6-pack"
        assert row["supply_duration_weeks"] == 24
        assert row["extraction_confidence"] == "high"


# ---------------------------------------------------------------------------
# get_recent_run_dates
# ---------------------------------------------------------------------------

class TestGetRecentRunDates:
    def test_returns_distinct_dates(self, db):
        db.insert(_result(run_date="2026-04-14", product_slug="prod-a"))
        db.insert(_result(run_date="2026-04-14", product_slug="prod-b"))
        db.insert(_result(run_date="2026-04-07", product_slug="prod-a"))
        dates = db.get_recent_run_dates()
        assert dates.count("2026-04-14") == 1

    def test_returns_newest_first(self, db):
        for week in ["2026-04-07", "2026-04-14", "2026-03-31"]:
            db.insert(_result(run_date=week))
        dates = db.get_recent_run_dates()
        assert dates == sorted(dates, reverse=True)

    def test_limit_respected(self, db):
        for i in range(1, 12):
            db.insert(_result(run_date=f"2026-01-{i:02d}"))
        dates = db.get_recent_run_dates(limit=5)
        assert len(dates) == 5

    def test_empty_db_returns_empty_list(self, db):
        assert db.get_recent_run_dates() == []
