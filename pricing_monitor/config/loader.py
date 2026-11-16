from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from models import CompetitorProduct

_CONFIG_DIR = Path(__file__).parent


@dataclass
class BrowserSettings:
    concurrency: int
    timeout_ms: int


@dataclass
class ApiSettings:
    extraction_model: str
    analysis_model: str
    extraction_concurrency: int


@dataclass
class StorageSettings:
    run_dir: str
    db_path: str
    history_weeks: int
    cleanup_after_weeks: int


@dataclass
class Settings:
    browser: BrowserSettings
    api: ApiSettings
    storage: StorageSettings


def load_settings(path: Path | None = None) -> Settings:
    """Load settings.yaml and return a typed Settings object."""
    settings_path = path or _CONFIG_DIR / "settings.yaml"
    raw = _read_yaml(settings_path)

    return Settings(
        browser=BrowserSettings(**raw["browser"]),
        api=ApiSettings(**raw["api"]),
        storage=StorageSettings(**raw["storage"]),
    )


def load_competitors(path: Path | None = None) -> list[CompetitorProduct]:
    """Load competitors.yaml and return a flat list of CompetitorProduct instances."""
    competitors_path = path or _CONFIG_DIR / "competitors.yaml"
    raw = _read_yaml(competitors_path)

    products: list[CompetitorProduct] = []
    for competitor in raw.get("competitors", []):
        _validate_competitor_entry(competitor)
        for product in competitor.get("products", []):
            _validate_product_entry(product, competitor["name"])
            products.append(
                CompetitorProduct(
                    competitor_name=competitor["name"],
                    competitor_slug=competitor["slug"],
                    rate_limit_delay_seconds=competitor.get("rate_limit_delay_seconds", 3.0),
                    viewport=competitor.get("viewport", {"width": 1280, "height": 900}),
                    canonical_name=product["canonical_name"],
                    slug=product["slug"],
                    url=product["url"],
                    category=product["category"],
                    expected_price_range=tuple(product["expected_price_range"]),
                )
            )
    return products


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at the top level: {path}")
    return data


def _validate_competitor_entry(entry: dict[str, Any]) -> None:
    required = {"name", "slug", "products"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"Competitor entry missing required fields: {missing}")
    if not isinstance(entry["products"], list):
        raise ValueError(f"'products' must be a list for competitor '{entry.get('name')}'")


def _validate_product_entry(entry: dict[str, Any], competitor_name: str) -> None:
    required = {"canonical_name", "slug", "url", "category", "expected_price_range"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(
            f"Product entry for '{competitor_name}' missing required fields: {missing}"
        )
    price_range = entry["expected_price_range"]
    if not (isinstance(price_range, list) and len(price_range) == 2):
        raise ValueError(
            f"'expected_price_range' must be a 2-element list for "
            f"'{entry.get('canonical_name')}' under '{competitor_name}'"
        )
