"""
Unit tests for scraper/screenshot.py.

Real Playwright is never launched — BrowserPool is replaced with a FakeBrowserPool
that either returns the fixture screenshot or raises an exception.
"""
import asyncio
import io
import pytest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

from models import CompetitorProduct
from scraper.screenshot import take_screenshot, screenshot_path, batch_screenshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product(**overrides) -> CompetitorProduct:
    base = dict(
        competitor_name="Chewy",
        competitor_slug="chewy",
        canonical_name="NexGard 10-24lbs 6-pack",
        slug="nexgard-10-24lb-6pk",
        url="https://www.chewy.com/nexgard/dp/52063",
        category="flea_tick_oral",
        expected_price_range=(150.0, 200.0),
        rate_limit_delay_seconds=0,  # no delay in tests
    )
    base.update(overrides)
    return CompetitorProduct(**base)


def _make_png(path: Path) -> None:
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


class FakePage:
    """Minimal page mock — goto/wait_for_selector/screenshot do nothing harmful."""
    async def goto(self, url, **kwargs): pass
    async def wait_for_selector(self, selector, **kwargs): pass
    async def screenshot(self, path=None, **kwargs):
        # Write a real PNG so downstream code can read it
        _make_png(Path(path))


class FakeContext:
    def __init__(self, raise_on_goto=False, raise_on_screenshot=False):
        self._raise_on_goto = raise_on_goto
        self._raise_on_screenshot = raise_on_screenshot

    async def new_page(self):
        page = FakePage()
        if self._raise_on_goto:
            page.goto = AsyncMock(side_effect=Exception("navigation failed"))
        if self._raise_on_screenshot:
            page.screenshot = AsyncMock(side_effect=Exception("screenshot failed"))
        return page

    async def close(self): pass


class FakeBrowserPool:
    def __init__(self, raise_on_goto=False, raise_on_screenshot=False):
        self._raise_on_goto = raise_on_goto
        self._raise_on_screenshot = raise_on_screenshot

    @asynccontextmanager
    async def new_context(self, viewport=None):
        yield FakeContext(
            raise_on_goto=self._raise_on_goto,
            raise_on_screenshot=self._raise_on_screenshot,
        )


# ---------------------------------------------------------------------------
# screenshot_path
# ---------------------------------------------------------------------------

class TestScreenshotPath:
    def test_filename_format(self, tmp_path):
        p = _product()
        result = screenshot_path(p, tmp_path)
        assert result.name == "chewy_nexgard-10-24lb-6pk.png"

    def test_path_under_screenshots_dir(self, tmp_path):
        p = _product()
        result = screenshot_path(p, tmp_path / "screenshots")
        assert result.parent == tmp_path / "screenshots"

    def test_different_competitor_slug(self, tmp_path):
        p = _product(competitor_slug="petmeds")
        result = screenshot_path(p, tmp_path)
        assert result.name == "petmeds_nexgard-10-24lb-6pk.png"


# ---------------------------------------------------------------------------
# take_screenshot — cache behaviour
# ---------------------------------------------------------------------------

class TestCacheBehaviour:
    async def test_returns_existing_png_without_browser_call(self, tmp_path):
        p = _product()
        dest = screenshot_path(p, tmp_path)
        _make_png(dest)  # pre-populate cache

        pool = FakeBrowserPool()
        result = await take_screenshot(p, tmp_path, pool)

        assert result == dest

    async def test_cached_result_does_not_call_new_context(self, tmp_path):
        p = _product()
        dest = screenshot_path(p, tmp_path)
        _make_png(dest)

        pool = FakeBrowserPool()
        # Patch new_context to assert it's never called
        original = pool.new_context
        calls = []

        @asynccontextmanager
        async def tracking_context(**kwargs):
            calls.append(1)
            async with original(**kwargs) as ctx:
                yield ctx

        pool.new_context = tracking_context
        await take_screenshot(p, tmp_path, pool)

        assert calls == [], "new_context should not be called on cache hit"

    async def test_missing_png_triggers_browser(self, tmp_path):
        p = _product()
        pool = FakeBrowserPool()

        result = await take_screenshot(p, tmp_path, pool)

        assert result is not None
        assert result.exists()
        assert result.name == "chewy_nexgard-10-24lb-6pk.png"


# ---------------------------------------------------------------------------
# take_screenshot — failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    async def test_navigation_error_returns_none(self, tmp_path):
        p = _product()
        pool = FakeBrowserPool(raise_on_goto=True)

        result = await take_screenshot(p, tmp_path, pool)

        assert result is None

    async def test_screenshot_error_returns_none(self, tmp_path):
        p = _product()
        pool = FakeBrowserPool(raise_on_screenshot=True)

        result = await take_screenshot(p, tmp_path, pool)

        assert result is None

    async def test_failure_does_not_write_partial_png(self, tmp_path):
        p = _product()
        pool = FakeBrowserPool(raise_on_goto=True)

        await take_screenshot(p, tmp_path, pool)

        dest = screenshot_path(p, tmp_path)
        assert not dest.exists()

    async def test_failure_does_not_raise(self, tmp_path):
        """Errors must be swallowed — caller checks return value."""
        p = _product()
        pool = FakeBrowserPool(raise_on_goto=True)

        # Should not raise
        result = await take_screenshot(p, tmp_path, pool)
        assert result is None


# ---------------------------------------------------------------------------
# take_screenshot — directory creation
# ---------------------------------------------------------------------------

class TestDirectoryCreation:
    async def test_creates_screenshots_dir_if_missing(self, tmp_path):
        p = _product()
        screenshots_dir = tmp_path / "runs" / "2026-04-14" / "screenshots"
        assert not screenshots_dir.exists()

        pool = FakeBrowserPool()
        await take_screenshot(p, screenshots_dir, pool)

        assert screenshots_dir.exists()


# ---------------------------------------------------------------------------
# batch_screenshot
# ---------------------------------------------------------------------------

class TestBatchScreenshot:
    async def test_returns_dict_keyed_by_slug(self, tmp_path):
        products = [
            _product(competitor_slug="chewy"),
            _product(competitor_slug="petmeds"),
        ]
        pool = FakeBrowserPool()

        results = await batch_screenshot(products, tmp_path, pool)

        assert "chewy_nexgard-10-24lb-6pk" in results
        assert "petmeds_nexgard-10-24lb-6pk" in results

    async def test_failure_does_not_abort_batch(self, tmp_path):
        products = [
            _product(competitor_slug="chewy"),
            _product(competitor_slug="petmeds"),
        ]

        call_count = 0

        @asynccontextmanager
        async def sometimes_fails(viewport=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield FakeContext(raise_on_goto=True)   # first product fails
            else:
                yield FakeContext()                      # second succeeds

        pool = FakeBrowserPool()
        pool.new_context = sometimes_fails

        results = await batch_screenshot(products, tmp_path, pool)

        assert len(results) == 2
        values = list(results.values())
        assert None in values          # one failure
        assert any(v is not None for v in values)  # one success

    async def test_all_cached_skips_browser(self, tmp_path):
        products = [_product(competitor_slug="chewy")]
        # Pre-populate cache
        _make_png(screenshot_path(products[0], tmp_path))

        pool = FakeBrowserPool()
        calls = []

        original = pool.new_context

        @asynccontextmanager
        async def tracking(viewport=None):
            calls.append(1)
            async with original(viewport=viewport) as ctx:
                yield ctx

        pool.new_context = tracking
        await batch_screenshot(products, tmp_path, pool)

        assert calls == []
