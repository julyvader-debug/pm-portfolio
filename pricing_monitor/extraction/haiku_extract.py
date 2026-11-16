from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path

from anthropic import AsyncAnthropic

from models import CompetitorProduct, ExtractionResult
from extraction.parser import parse_haiku_response
from extraction.prompts import SYSTEM_PROMPT, build_user_prompt

# Anthropic image upload limit — resize if exceeded
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


async def extract_from_screenshot(
    product: CompetitorProduct,
    screenshot_path: Path,
    run_dir: Path,
    client: AsyncAnthropic,
    model: str = "claude-haiku-4-5-20251001",
    semaphore: asyncio.Semaphore | None = None,
) -> ExtractionResult:
    """
    Extract price data from a single screenshot using Haiku vision.
    Returns an ExtractionResult with status success/extraction_failed.
    If the screenshot file is missing the result has status scrape_failed.
    """
    base = dict(
        run_date=_run_date_from_dir(run_dir),
        competitor_slug=product.competitor_slug,
        product_slug=product.slug,
        canonical_name=product.canonical_name,
    )

    if not screenshot_path.exists():
        return ExtractionResult(
            **base,
            status="scrape_failed",
            error="screenshot_not_found",
        )

    image_data = _load_and_encode(screenshot_path)

    async def _call() -> ExtractionResult:
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": build_user_prompt(
                                    product.canonical_name,
                                    product.competitor_name,
                                ),
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:
            return ExtractionResult(
                **base,
                status="extraction_failed",
                error=f"api_error: {exc}",
            )

        raw_json = response.content[0].text
        result = parse_haiku_response(
            raw_json=raw_json,
            extracted_at=datetime.now(timezone.utc).isoformat(),
            **base,
            expected_price_range=product.expected_price_range,
        )
        return result

    if semaphore:
        async with semaphore:
            return await _call()
    return await _call()


async def batch_extract(
    products: list[CompetitorProduct],
    screenshot_dir: Path,
    run_dir: Path,
    client: AsyncAnthropic,
    model: str = "claude-haiku-4-5-20251001",
    concurrency: int = 5,
) -> list[ExtractionResult]:
    """
    Extract prices for all products in parallel, bounded by concurrency semaphore.
    Screenshot filenames follow the pattern: {competitor_slug}_{product_slug}.png
    """
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        extract_from_screenshot(
            product=product,
            screenshot_path=screenshot_dir / f"{product.competitor_slug}_{product.slug}.png",
            run_dir=run_dir,
            client=client,
            model=model,
            semaphore=semaphore,
        )
        for product in products
    ]
    return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_date_from_dir(run_dir: Path) -> str:
    """Use the run directory name as run_date (expected: YYYY-MM-DD)."""
    return run_dir.name


def _load_and_encode(path: Path) -> str:
    """Read image file, resize if over 5MB, return base64 string."""
    data = path.read_bytes()
    if len(data) > _MAX_IMAGE_BYTES:
        data = _resize_image(data)
    return base64.standard_b64encode(data).decode("utf-8")


def _resize_image(data: bytes) -> bytes:
    """Resize image so it fits under the API size limit."""
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(data))
    # Scale down by half until under limit
    while True:
        new_size = (img.width // 2, img.height // 2)
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        if len(data) <= _MAX_IMAGE_BYTES or img.width < 100:
            break
    return data
