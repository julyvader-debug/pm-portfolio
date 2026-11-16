"""
Integration test for scheduler/runner.py — run_once().

Uses:
  - FakeBrowserPool: writes a real PNG instead of launching Chromium
  - Mocked AsyncAnthropic: returns canned Haiku / Sonnet responses
  - Temp directories for run_dir and DB
  - Real config/settings objects (no YAML files needed)
"""
import io
import json
import pytest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from config.loader import Settings, BrowserSettings, ApiSettings, StorageSettings
from models import CompetitorProduct
from scheduler.runner import run_once
from storage.db import PriceDB


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _settings() -> Settings:
    return Settings(
        browser=BrowserSettings(concurrency=3, timeout_ms=5000),
        api=ApiSettings(
            extraction_model="claude-haiku-4-5-20251001",
            analysis_model="claude-sonnet-4-6",
            extraction_concurrency=5,
        ),
        storage=StorageSettings(
            run_dir="data/runs",
            db_path="data/pricing.db",
            history_weeks=8,
            cleanup_after_weeks=12,
        ),
    )


def _product(competitor_slug: str = "chewy") -> CompetitorProduct:
    return CompetitorProduct(
        competitor_name=competitor_slug.title(),
        competitor_slug=competitor_slug,
        canonical_name="NexGard 10-24lbs 6-pack",
        slug="nexgard-10-24lb-6pk",
        url=f"https://{competitor_slug}.com/nexgard",
        category="flea_tick_oral",
        expected_price_range=(150.0, 200.0),
        rate_limit_delay_seconds=0,  # no sleep in tests
    )


def _make_png(path: Path) -> None:
    img = Image.new("RGB", (100, 100), color=(200, 220, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# FakeBrowserPool
# ---------------------------------------------------------------------------

class _FakePage:
    def __init__(self, screenshots_dir: Path, filename: str):
        self._screenshots_dir = screenshots_dir
        self._filename = filename

    async def goto(self, url, **kwargs): pass
    async def wait_for_selector(self, selector, **kwargs): pass

    async def screenshot(self, path=None, **kwargs):
        _make_png(Path(path))


class _FakeContext:
    def __init__(self, screenshots_dir: Path, filename: str):
        self._screenshots_dir = screenshots_dir
        self._filename = filename

    async def new_page(self):
        return _FakePage(self._screenshots_dir, self._filename)

    async def close(self): pass


class FakeBrowserPool:
    """
    Replaces BrowserPool. new_context() yields a fake context whose page.screenshot()
    writes a real PNG to the given path — satisfying the cache-check in take_screenshot().
    """
    def __init__(self, screenshots_dir: Path):
        self._screenshots_dir = screenshots_dir

    @asynccontextmanager
    async def new_context(self, viewport=None):
        yield _FakeContext(self._screenshots_dir, "")


# ---------------------------------------------------------------------------
# Mock Anthropic client
# ---------------------------------------------------------------------------

HAIKU_RESPONSE = {
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

SONNET_MARKDOWN = """## Executive Summary
NexGard prices stable this week.

## Product Comparison
| Product | Competitor | Standard Price |
|---------|-----------|---------------|
| NexGard | chewy | $179.99 |

## Price Trend Analysis
Prices unchanged week-over-week.

## Notable Findings
- Chewy subscription is $18 cheaper than standard.

## Data Quality Notes
All extractions high confidence."""

SONNET_CSV = [
    {
        "run_date": "2026-04-14",
        "competitor_slug": "chewy",
        "product_slug": "nexgard-10-24lb-6pk",
        "canonical_name": "NexGard 10-24lbs 6-pack",
        "category": "flea_tick_oral",
        "price_standard": 179.99,
        "price_sale": None,
        "price_subscription": 161.99,
        "price_per_month": 27.0,
        "vs_previous_price": None,
        "in_stock": True,
        "unit_size": "6-pack",
        "supply_duration_weeks": 24,
        "confidence": "high",
        "scrape_status": "success",
    }
]

SONNET_RESPONSE = (
    f"{SONNET_MARKDOWN}\n\n"
    f"<CSV_DATA>\n{json.dumps(SONNET_CSV, indent=2)}\n</CSV_DATA>"
)


def _mock_anthropic(haiku_json=None, sonnet_text=None):
    """
    Returns a mock AsyncAnthropic client.
    Routes by model: haiku → HAIKU_RESPONSE, sonnet → SONNET_RESPONSE.
    """
    haiku_json = haiku_json or HAIKU_RESPONSE
    sonnet_text = sonnet_text or SONNET_RESPONSE

    async def _create(**kwargs):
        model = kwargs.get("model", "")
        text = (
            json.dumps(haiku_json)
            if "haiku" in model
            else sonnet_text
        )
        block = MagicMock()
        block.text = text
        msg = MagicMock()
        msg.content = [block]
        return msg

    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=_create)
    return client


# ---------------------------------------------------------------------------
# run_once tests
# ---------------------------------------------------------------------------

@pytest.fixture
def run_dir(tmp_path) -> Path:
    d = tmp_path / "2026-04-14"
    d.mkdir()
    return d


@pytest.fixture
def db(tmp_path) -> PriceDB:
    return PriceDB(tmp_path / "pricing.db")


class TestRunOnce:
    async def test_returns_analysis_report(self, run_dir, db):
        products = [_product("chewy")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        report = await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        assert report.run_date == "2026-04-14"
        assert report.success_count == 1

    async def test_screenshot_written(self, run_dir, db):
        products = [_product("chewy")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        assert (run_dir / "screenshots" / "chewy_nexgard-10-24lb-6pk.png").exists()

    async def test_output_files_written(self, run_dir, db):
        products = [_product("chewy")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        assert (run_dir / "report.md").exists()
        assert (run_dir / "report.csv").exists()
        assert (run_dir / "failures.json").exists()

    async def test_results_persisted_to_db(self, run_dir, db):
        products = [_product("chewy")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        rows = db.get_trend("nexgard-10-24lb-6pk")
        assert len(rows) == 1
        assert rows[0]["competitor_slug"] == "chewy"
        assert rows[0]["price_standard"] == 179.99

    async def test_multiple_competitors(self, run_dir, db):
        products = [_product("chewy"), _product("petmeds")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        report = await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        assert len(report.extraction_results) == 2
        slugs = {r.competitor_slug for r in report.extraction_results}
        assert slugs == {"chewy", "petmeds"}

    async def test_cached_screenshot_not_re_scraped(self, run_dir, db):
        """If PNG already exists, browser should not be called for that product."""
        products = [_product("chewy")]
        screenshots_dir = run_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        _make_png(screenshots_dir / "chewy_nexgard-10-24lb-6pk.png")

        new_context_calls = []

        pool = FakeBrowserPool(screenshots_dir)
        original = pool.new_context

        @asynccontextmanager
        async def tracking(viewport=None):
            new_context_calls.append(1)
            async with original(viewport=viewport) as ctx:
                yield ctx

        pool.new_context = tracking

        await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool,
        )

        assert new_context_calls == [], "cached screenshot should not trigger browser"

    async def test_scrape_failure_does_not_abort_run(self, run_dir, db):
        """A product whose screenshot fails still completes the run for other products."""
        products = [_product("chewy"), _product("petmeds")]

        call_count = 0

        class PartialFailPool:
            @asynccontextmanager
            async def new_context(self, viewport=None):
                nonlocal call_count
                call_count += 1
                ctx = _FakeContext(run_dir / "screenshots", "")
                if call_count == 1:
                    # First call: page.goto raises
                    page = await ctx.new_page()
                    page.goto = AsyncMock(side_effect=Exception("blocked"))
                    ctx.new_page = AsyncMock(return_value=page)
                yield ctx

        report = await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=PartialFailPool(),
        )

        assert len(report.extraction_results) == 2
        statuses = {r.status for r in report.extraction_results}
        assert "scrape_failed" in statuses

    async def test_haiku_api_failure_does_not_abort_run(self, run_dir, db):
        """Haiku extraction failure for one product shouldn't crash the run."""
        products = [_product("chewy")]
        pool = FakeBrowserPool(run_dir / "screenshots")

        call_count = 0

        async def _create_bad(**kwargs):
            nonlocal call_count
            call_count += 1
            if "haiku" in kwargs.get("model", "") and call_count == 1:
                raise Exception("haiku rate limit")
            # Sonnet call succeeds
            block = MagicMock()
            block.text = SONNET_RESPONSE
            msg = MagicMock()
            msg.content = [block]
            return msg

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=_create_bad)

        report = await run_once(
            run_date="2026-04-14",
            run_dir=run_dir,
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=client,
            browser_pool=pool,
        )

        assert len(report.extraction_results) == 1
        assert report.extraction_results[0].status == "extraction_failed"

    async def test_history_passed_to_sonnet(self, run_dir, db):
        """Second run should find first run's data in history."""
        products = [_product("chewy")]

        # First run
        pool1 = FakeBrowserPool(run_dir / "screenshots")
        await run_once(
            run_date="2026-04-07",
            run_dir=run_dir.parent / "2026-04-07",
            products=products,
            settings=_settings(),
            db=db,
            anthropic_client=_mock_anthropic(),
            browser_pool=pool1,
        )

        # Second run — history should contain first run
        pool2 = FakeBrowserPool(run_dir / "screenshots")
        history_sent = {}

        original_analyze = __import__(
            "analysis.sonnet_analyze", fromlist=["analyze_run"]
        ).analyze_run

        async def capture_analyze(run_date, extraction_results, history_by_product, **kwargs):
            history_sent.update(history_by_product)
            return await original_analyze(
                run_date=run_date,
                extraction_results=extraction_results,
                history_by_product=history_by_product,
                **kwargs,
            )

        import scheduler.runner as runner_module
        original = runner_module.analyze_run
        runner_module.analyze_run = capture_analyze

        try:
            await run_once(
                run_date="2026-04-14",
                run_dir=run_dir,
                products=products,
                settings=_settings(),
                db=db,
                anthropic_client=_mock_anthropic(),
                browser_pool=pool2,
            )
        finally:
            runner_module.analyze_run = original

        assert "nexgard-10-24lb-6pk" in history_sent
        run_dates = {r["run_date"] for r in history_sent["nexgard-10-24lb-6pk"]}
        # Prior run persisted to DB; history includes both weeks
        assert "2026-04-07" in run_dates
