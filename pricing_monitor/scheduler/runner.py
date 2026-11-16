from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from anthropic import AsyncAnthropic

from analysis.sonnet_analyze import analyze_run
from config.loader import Settings, load_competitors, load_settings
from extraction.haiku_extract import batch_extract
from models import AnalysisReport, CompetitorProduct
from scraper.browser import BrowserPool
from scraper.screenshot import batch_screenshot
from storage.db import PriceDB
from storage.export import write_all

logger = logging.getLogger(__name__)


async def run_once(
    run_date: str,
    run_dir: Path,
    products: list[CompetitorProduct],
    settings: Settings,
    db: PriceDB,
    anthropic_client: AsyncAnthropic,
    browser_pool: BrowserPool,
) -> AnalysisReport:
    """
    Execute all 6 pipeline phases for a single run.

    Phases:
      1. SCRAPE   — take screenshots (cache-first, parallel, semaphore-bounded)
      2. EXTRACT  — Haiku vision → ExtractionResults (parallel, semaphore-bounded)
      3. PERSIST  — append results to SQLite
      4. ANALYZE  — fetch history + call Sonnet → AnalysisReport
      5. OUTPUT   — write report.md, report.csv, failures.json
      6. (COMMIT  — handled externally by GitHub Actions)
    """
    screenshots_dir = run_dir / "screenshots"
    run_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # PHASE 1: SCRAPE                                                      #
    # ------------------------------------------------------------------ #
    logger.info("[phase 1/5] scraping %d products", len(products))
    await batch_screenshot(
        products=products,
        screenshots_dir=screenshots_dir,
        browser_pool=browser_pool,
    )

    # ------------------------------------------------------------------ #
    # PHASE 2: EXTRACT                                                     #
    # ------------------------------------------------------------------ #
    logger.info("[phase 2/5] extracting prices via Haiku")
    extraction_results = await batch_extract(
        products=products,
        screenshot_dir=screenshots_dir,
        run_dir=run_dir,
        client=anthropic_client,
        model=settings.api.extraction_model,
        concurrency=settings.api.extraction_concurrency,
    )

    successes = sum(1 for r in extraction_results if r.status == "success")
    failures = len(extraction_results) - successes
    logger.info(
        "[phase 2/5] extraction complete: %d success, %d failed",
        successes,
        failures,
    )

    # ------------------------------------------------------------------ #
    # PHASE 3: PERSIST                                                     #
    # ------------------------------------------------------------------ #
    logger.info("[phase 3/5] persisting %d rows to DB", len(extraction_results))
    db.insert_many(extraction_results)

    # ------------------------------------------------------------------ #
    # PHASE 4: ANALYZE                                                     #
    # ------------------------------------------------------------------ #
    logger.info("[phase 4/5] fetching history and calling Sonnet")
    product_slugs = list({p.slug for p in products})
    history_by_product = {
        slug: db.get_trend(slug, weeks=settings.storage.history_weeks)
        for slug in product_slugs
    }

    report = await analyze_run(
        run_date=run_date,
        extraction_results=extraction_results,
        history_by_product=history_by_product,
        client=anthropic_client,
        model=settings.api.analysis_model,
    )

    # ------------------------------------------------------------------ #
    # PHASE 5: OUTPUT                                                      #
    # ------------------------------------------------------------------ #
    logger.info("[phase 5/5] writing outputs to %s", run_dir)
    write_all(run_dir, report)

    logger.info(
        "run complete — %d success, %d failed, report at %s",
        report.success_count,
        report.failure_count,
        run_dir,
    )
    return report


async def run(
    run_date: str | None = None,
    data_dir: Path = Path("data"),
    competitors_path: Path | None = None,
    settings_path: Path | None = None,
) -> AnalysisReport:
    """
    Top-level entry point: load config, create dependencies, call run_once().
    Used by __main__.py and GitHub Actions.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    today = run_date or date.today().isoformat()
    settings = load_settings(settings_path)
    products = load_competitors(competitors_path)

    run_dir = data_dir / "runs" / today
    db = PriceDB(data_dir / settings.storage.db_path.lstrip("data/"))

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = AsyncAnthropic(api_key=api_key)

    async with BrowserPool(concurrency=settings.browser.concurrency) as browser_pool:
        return await run_once(
            run_date=today,
            run_dir=run_dir,
            products=products,
            settings=settings,
            db=db,
            anthropic_client=client,
            browser_pool=browser_pool,
        )
