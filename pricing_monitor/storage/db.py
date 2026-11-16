from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from models import ExtractionResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_observations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date                TEXT    NOT NULL,
    competitor_slug         TEXT    NOT NULL,
    product_slug            TEXT    NOT NULL,
    canonical_name          TEXT    NOT NULL,
    price_standard          REAL,
    price_sale              REAL,
    price_subscription      REAL,
    price_per_month         REAL,
    in_stock                INTEGER,
    unit_size               TEXT,
    supply_duration_weeks   INTEGER,
    extraction_confidence   TEXT,
    scrape_status           TEXT    NOT NULL,
    extracted_at            TEXT,
    created_at              TEXT    DEFAULT (datetime('now'))
);
"""

_INSERT = """
INSERT INTO price_observations (
    run_date, competitor_slug, product_slug, canonical_name,
    price_standard, price_sale, price_subscription, price_per_month,
    in_stock, unit_size, supply_duration_weeks,
    extraction_confidence, scrape_status, extracted_at
) VALUES (
    :run_date, :competitor_slug, :product_slug, :canonical_name,
    :price_standard, :price_sale, :price_subscription, :price_per_month,
    :in_stock, :unit_size, :supply_duration_weeks,
    :extraction_confidence, :scrape_status, :extracted_at
);
"""

_TREND_QUERY = """
SELECT
    run_date, competitor_slug, product_slug, canonical_name,
    price_standard, price_sale, price_subscription, price_per_month,
    in_stock, unit_size, supply_duration_weeks,
    extraction_confidence, scrape_status, extracted_at
FROM price_observations
WHERE product_slug = :product_slug
  AND scrape_status = 'success'
ORDER BY run_date DESC
LIMIT :limit;
"""

_RUNS_QUERY = """
SELECT DISTINCT run_date
FROM price_observations
ORDER BY run_date DESC
LIMIT :limit;
"""


class PriceDB:
    """Append-only SQLite store for price observations."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert(self, result: ExtractionResult) -> None:
        """Append one ExtractionResult row. Never updates existing rows."""
        row = {
            "run_date": result.run_date,
            "competitor_slug": result.competitor_slug,
            "product_slug": result.product_slug,
            "canonical_name": result.canonical_name,
            "price_standard": result.price_standard,
            "price_sale": result.price_sale,
            "price_subscription": result.price_subscription,
            "price_per_month": result.price_per_month,
            "in_stock": int(result.in_stock) if result.in_stock is not None else None,
            "unit_size": result.unit_size,
            "supply_duration_weeks": result.supply_duration_weeks,
            "extraction_confidence": result.confidence,
            "scrape_status": result.status,
            "extracted_at": result.extracted_at
            or datetime.now(timezone.utc).isoformat(),
        }
        with self._conn() as conn:
            conn.execute(_INSERT, row)

    def insert_many(self, results: list[ExtractionResult]) -> None:
        """Append multiple results in a single transaction."""
        for result in results:
            self.insert(result)

    def get_trend(
        self, product_slug: str, weeks: int = 8
    ) -> list[dict]:
        """
        Return up to `weeks` most-recent successful observations for a product,
        newest first. Only rows with scrape_status='success' are included.
        """
        with self._conn() as conn:
            rows = conn.execute(
                _TREND_QUERY,
                {"product_slug": product_slug, "limit": weeks},
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_run_dates(self, limit: int = 8) -> list[str]:
        """Return up to `limit` most-recent distinct run dates, newest first."""
        with self._conn() as conn:
            rows = conn.execute(_RUNS_QUERY, {"limit": limit}).fetchall()
        return [r["run_date"] for r in rows]
