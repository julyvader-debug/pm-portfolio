from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class CompetitorProduct(BaseModel):
    """A single product entry from competitors.yaml, enriched with its parent competitor info."""

    competitor_name: str
    competitor_slug: str
    canonical_name: str
    slug: str
    url: str
    category: str
    expected_price_range: tuple[float, float]
    rate_limit_delay_seconds: float = 3.0
    viewport: dict[str, int] = Field(default_factory=lambda: {"width": 1280, "height": 900})

    @model_validator(mode="after")
    def validate_price_range(self) -> CompetitorProduct:
        low, high = self.expected_price_range
        if low >= high:
            raise ValueError(
                f"expected_price_range low ({low}) must be less than high ({high})"
            )
        return self


ExtractionStatus = Literal["success", "scrape_failed", "extraction_failed"]
ExtractionConfidence = Literal["high", "medium", "low"]


class ExtractionResult(BaseModel):
    """Price data extracted from one competitor product page screenshot."""

    run_date: str
    competitor_slug: str
    product_slug: str
    canonical_name: str
    status: ExtractionStatus

    # Populated on success
    price_standard: Optional[float] = None
    price_sale: Optional[float] = None
    price_subscription: Optional[float] = None
    price_per_month: Optional[float] = None
    in_stock: Optional[bool] = None
    unit_size: Optional[str] = None
    supply_duration_weeks: Optional[int] = None
    confidence: Optional[ExtractionConfidence] = None

    # Populated on failure or low-confidence pages
    error: Optional[str] = None
    extracted_at: Optional[str] = None

    @property
    def best_price(self) -> Optional[float]:
        """Return the lowest available price: subscription < sale < standard."""
        return (
            self.price_subscription
            or self.price_sale
            or self.price_standard
        )

    def is_price_in_range(self, expected_range: tuple[float, float]) -> bool:
        """Return False if best_price exists but falls outside expected_range."""
        price = self.best_price
        if price is None:
            return True
        low, high = expected_range
        return low <= price <= high


class AnalysisReport(BaseModel):
    """Output produced by Sonnet after analyzing a full run."""

    run_date: str
    markdown: str
    csv_rows: list[dict]
    extraction_results: list[ExtractionResult]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.extraction_results if r.status == "success")

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.extraction_results if r.status != "success")
