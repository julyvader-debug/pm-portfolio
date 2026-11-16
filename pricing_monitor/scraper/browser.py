from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

# Rotate through a small set of realistic desktop user-agents
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    ),
]


class BrowserPool:
    """
    Manages a single Chromium instance with semaphore-bounded browser contexts.

    Usage:
        async with BrowserPool(concurrency=3) as pool:
            async with pool.new_context(viewport={"width": 1280, "height": 900}) as ctx:
                page = await ctx.new_page()
                ...
    """

    def __init__(self, concurrency: int = 3) -> None:
        self._concurrency = concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> BrowserPool:
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @asynccontextmanager
    async def new_context(
        self, viewport: dict[str, int] | None = None
    ) -> AsyncGenerator[BrowserContext, None]:
        """
        Acquire the semaphore, create a fresh browser context, yield it,
        then close the context and release the semaphore.
        """
        assert self._browser is not None, "BrowserPool must be used as async context manager"
        assert self._semaphore is not None

        vp = viewport or {"width": 1280, "height": 900}
        user_agent = random.choice(_USER_AGENTS)

        async with self._semaphore:
            context = await self._browser.new_context(
                viewport=vp,
                user_agent=user_agent,
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            try:
                yield context
            finally:
                await context.close()
