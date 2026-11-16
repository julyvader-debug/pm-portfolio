from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from models import CompetitorProduct
from scraper.browser import BrowserPool

logger = logging.getLogger(__name__)

# CSS selector that indicates a price is present on the page.
# We wait up to PRICE_SELECTOR_TIMEOUT_MS for it; then screenshot anyway.
_PRICE_SELECTOR = "[class*='price'], [data-testid*='price'], .price, #price"
_PRICE_SELECTOR_TIMEOUT_MS = 5_000
_PAGE_LOAD_TIMEOUT_MS = 30_000


def screenshot_path(product: CompetitorProduct, screenshots_dir: Path) -> Path:
    """Return the canonical PNG path for a product screenshot."""
    return screenshots_dir / f"{product.competitor_slug}_{product.slug}.png"


async def take_screenshot(
    product: CompetitorProduct,
    screenshots_dir: Path,
    browser_pool: BrowserPool,
) -> Path | None:
    """
    Navigate to product.url and save a screenshot to screenshots_dir.

    Cache-first: if the PNG already exists, return its path immediately.
    Single attempt only — on any failure, log and return None.
    Applies per-domain delay after a successful screenshot.

    Returns the path to the PNG on success, None on failure.
    """
    dest = screenshot_path(product, screenshots_dir)

    # Cache check — skip if already captured this run
    if dest.exists():
        logger.info("cache hit: %s", dest.name)
        return dest

    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with browser_pool.new_context(viewport=product.viewport) as context:
            page = await context.new_page()

            await page.goto(
                product.url,
                timeout=_PAGE_LOAD_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )

            # Wait for a price element — take screenshot regardless of outcome
            try:
                await page.wait_for_selector(
                    _PRICE_SELECTOR,
                    timeout=_PRICE_SELECTOR_TIMEOUT_MS,
                )
            except Exception:
                logger.warning(
                    "price selector not found within %dms for %s/%s — screenshotting anyway",
                    _PRICE_SELECTOR_TIMEOUT_MS,
                    product.competitor_slug,
                    product.slug,
                )

            await page.screenshot(path=str(dest), full_page=False)

        # Per-domain rate-limit delay (outside context so browser is already closed)
        await asyncio.sleep(product.rate_limit_delay_seconds)

        logger.info("screenshot saved: %s", dest.name)
        return dest

    except Exception as exc:
        logger.error(
            "screenshot failed for %s/%s: %s",
            product.competitor_slug,
            product.slug,
            exc,
        )
        return None


async def batch_screenshot(
    products: list[CompetitorProduct],
    screenshots_dir: Path,
    browser_pool: BrowserPool,
) -> dict[str, Path | None]:
    """
    Take screenshots for all products concurrently (semaphore managed by BrowserPool).
    Returns a dict mapping '{competitor_slug}_{product_slug}' → Path or None.
    """
    async def _capture(product: CompetitorProduct) -> tuple[str, Path | None]:
        key = f"{product.competitor_slug}_{product.slug}"
        path = await take_screenshot(product, screenshots_dir, browser_pool)
        return key, path

    results = await asyncio.gather(*[_capture(p) for p in products])
    return dict(results)
