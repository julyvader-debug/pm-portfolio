"""
Integration tests for haiku_extract.py.

Anthropic client is mocked at the SDK boundary — no real API calls are made.
A small valid PNG is used as the fixture screenshot.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from models import CompetitorProduct
from extraction.haiku_extract import extract_from_screenshot, batch_extract


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def product() -> CompetitorProduct:
    return CompetitorProduct(
        competitor_name="Chewy",
        competitor_slug="chewy",
        canonical_name="NexGard 10-24lbs 6-pack",
        slug="nexgard-10-24lb-6pk",
        url="https://www.chewy.com/nexgard/dp/52063",
        category="flea_tick_oral",
        expected_price_range=(150.0, 200.0),
    )


@pytest.fixture
def run_dir(tmp_path) -> Path:
    d = tmp_path / "2026-04-14"
    d.mkdir()
    return d


def _mock_client(response_json: dict) -> AsyncMock:
    """Build a mock AsyncAnthropic client that returns response_json as text."""
    text_block = MagicMock()
    text_block.text = json.dumps(response_json)

    message = MagicMock()
    message.content = [text_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=message)
    return client


GOOD_HAIKU_RESPONSE = {
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

class TestExtractFromScreenshot:
    async def test_returns_success_status(self, product, run_dir, fixture_screenshot_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        result = await extract_from_screenshot(product, screenshot, run_dir, client)

        assert result.status == "success"

    async def test_prices_extracted(self, product, run_dir, fixture_screenshot_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        result = await extract_from_screenshot(product, screenshot, run_dir, client)

        assert result.price_standard == 179.99
        assert result.price_subscription == 161.99
        assert result.price_per_month == 27.0

    async def test_identifiers_set_correctly(self, product, run_dir, fixture_screenshot_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        result = await extract_from_screenshot(product, screenshot, run_dir, client)

        assert result.run_date == "2026-04-14"
        assert result.competitor_slug == "chewy"
        assert result.product_slug == "nexgard-10-24lb-6pk"
        assert result.canonical_name == "NexGard 10-24lbs 6-pack"

    async def test_api_called_with_base64_image(self, product, run_dir, fixture_screenshot_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        await extract_from_screenshot(product, screenshot, run_dir, client)

        _, call_kwargs = client.messages.create.call_args
        content = call_kwargs["messages"][0]["content"]
        image_block = content[0]
        assert image_block["type"] == "image"
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["media_type"] == "image/png"
        assert len(image_block["source"]["data"]) > 0

    async def test_correct_model_used(self, product, run_dir, fixture_screenshot_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        await extract_from_screenshot(product, screenshot, run_dir, client,
                                      model="claude-haiku-4-5-20251001")

        _, call_kwargs = client.messages.create.call_args
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Missing screenshot → scrape_failed (not a crash)
# ---------------------------------------------------------------------------

class TestMissingScreenshot:
    async def test_missing_screenshot_returns_scrape_failed(self, product, run_dir):
        client = _mock_client(GOOD_HAIKU_RESPONSE)
        missing = Path("/nonexistent/path/screenshot.png")

        result = await extract_from_screenshot(product, missing, run_dir, client)

        assert result.status == "scrape_failed"
        assert result.error == "screenshot_not_found"
        client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Malformed JSON from Haiku → extraction_failed (not a crash)
# ---------------------------------------------------------------------------

class TestMalformedHaikuResponse:
    async def _extract_with_raw_text(self, raw_text, product, run_dir, fixture_screenshot_dir):
        text_block = MagicMock()
        text_block.text = raw_text
        message = MagicMock()
        message.content = [text_block]
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=message)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"
        return await extract_from_screenshot(product, screenshot, run_dir, client)

    async def test_invalid_json_becomes_extraction_failed(
        self, product, run_dir, fixture_screenshot_dir
    ):
        result = await self._extract_with_raw_text(
            "Sorry, I cannot extract prices from this image.",
            product, run_dir, fixture_screenshot_dir,
        )
        assert result.status == "extraction_failed"
        assert "json_parse_error" in result.error

    async def test_blocked_page_becomes_extraction_failed(
        self, product, run_dir, fixture_screenshot_dir
    ):
        blocked = {**GOOD_HAIKU_RESPONSE, "error": "page_blocked", "price_standard": None, "confidence": "low"}
        result = await self._extract_with_raw_text(
            json.dumps(blocked),
            product, run_dir, fixture_screenshot_dir,
        )
        assert result.status == "extraction_failed"
        assert result.error == "page_blocked"

    async def test_missing_confidence_becomes_extraction_failed(
        self, product, run_dir, fixture_screenshot_dir
    ):
        no_conf = {k: v for k, v in GOOD_HAIKU_RESPONSE.items() if k != "confidence"}
        result = await self._extract_with_raw_text(
            json.dumps(no_conf),
            product, run_dir, fixture_screenshot_dir,
        )
        assert result.status == "extraction_failed"
        assert result.error == "missing_confidence"


# ---------------------------------------------------------------------------
# API error → extraction_failed (not a crash)
# ---------------------------------------------------------------------------

class TestApiError:
    async def test_api_exception_becomes_extraction_failed(
        self, product, run_dir, fixture_screenshot_dir
    ):
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("connection timeout"))
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        result = await extract_from_screenshot(product, screenshot, run_dir, client)

        assert result.status == "extraction_failed"
        assert "api_error" in result.error
        assert "connection timeout" in result.error


# ---------------------------------------------------------------------------
# Out-of-range price → success but confidence forced to low
# ---------------------------------------------------------------------------

class TestPriceRangeDowngrade:
    async def test_out_of_range_price_downgrades_confidence(
        self, product, run_dir, fixture_screenshot_dir
    ):
        # product expected_price_range is (150, 200) — price 50 is way below
        low_price = {**GOOD_HAIKU_RESPONSE, "price_standard": 50.0, "price_subscription": None}
        client = _mock_client(low_price)
        screenshot = fixture_screenshot_dir / "chewy_nexgard-10-24lb-6pk.png"

        result = await extract_from_screenshot(product, screenshot, run_dir, client)

        assert result.status == "success"
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# batch_extract
# ---------------------------------------------------------------------------

class TestBatchExtract:
    def _make_product(self, competitor_slug: str) -> CompetitorProduct:
        return CompetitorProduct(
            competitor_name=competitor_slug.title(),
            competitor_slug=competitor_slug,
            canonical_name="NexGard 10-24lbs 6-pack",
            slug="nexgard-10-24lb-6pk",
            url=f"https://{competitor_slug}.com/nexgard",
            category="flea_tick_oral",
            expected_price_range=(150.0, 200.0),
        )

    async def test_returns_one_result_per_product(self, run_dir, fixture_screenshot_dir):
        products = [
            self._make_product("chewy"),
            self._make_product("petmeds"),
        ]
        client = _mock_client(GOOD_HAIKU_RESPONSE)

        results = await batch_extract(
            products=products,
            screenshot_dir=fixture_screenshot_dir,
            run_dir=run_dir,
            client=client,
        )

        assert len(results) == 2

    async def test_missing_screenshot_does_not_abort_batch(self, run_dir, fixture_screenshot_dir):
        products = [
            self._make_product("chewy"),          # fixture exists
            self._make_product("missing_site"),   # no fixture
        ]
        client = _mock_client(GOOD_HAIKU_RESPONSE)

        results = await batch_extract(
            products=products,
            screenshot_dir=fixture_screenshot_dir,
            run_dir=run_dir,
            client=client,
        )

        assert len(results) == 2
        statuses = {r.status for r in results}
        assert "success" in statuses
        assert "scrape_failed" in statuses

    async def test_run_date_derived_from_run_dir(self, run_dir, fixture_screenshot_dir):
        products = [self._make_product("chewy")]
        client = _mock_client(GOOD_HAIKU_RESPONSE)

        results = await batch_extract(
            products=products,
            screenshot_dir=fixture_screenshot_dir,
            run_dir=run_dir,
            client=client,
        )

        assert results[0].run_date == "2026-04-14"
