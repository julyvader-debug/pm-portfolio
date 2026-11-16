import pytest
from pathlib import Path
import yaml
import tempfile
import os

from config.loader import load_settings, load_competitors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


VALID_COMPETITORS = {
    "competitors": [
        {
            "name": "Chewy",
            "slug": "chewy",
            "rate_limit_delay_seconds": 3,
            "viewport": {"width": 1280, "height": 900},
            "products": [
                {
                    "canonical_name": "NexGard 10-24lbs 6-pack",
                    "slug": "nexgard-10-24lb-6pk",
                    "url": "https://www.chewy.com/nexgard/dp/52063",
                    "category": "flea_tick_oral",
                    "expected_price_range": [150, 200],
                }
            ],
        }
    ]
}

VALID_SETTINGS = {
    "browser": {"concurrency": 3, "timeout_ms": 5000},
    "api": {
        "extraction_model": "claude-haiku-4-5-20251001",
        "analysis_model": "claude-sonnet-4-6",
        "extraction_concurrency": 5,
    },
    "storage": {
        "run_dir": "data/runs",
        "db_path": "data/pricing.db",
        "history_weeks": 8,
        "cleanup_after_weeks": 12,
    },
}


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------

class TestLoadSettings:
    def test_loads_valid_settings(self, tmp_path):
        path = _write_yaml(tmp_path, "settings.yaml", VALID_SETTINGS)
        settings = load_settings(path)
        assert settings.browser.concurrency == 3
        assert settings.browser.timeout_ms == 5000
        assert settings.api.extraction_model == "claude-haiku-4-5-20251001"
        assert settings.api.analysis_model == "claude-sonnet-4-6"
        assert settings.api.extraction_concurrency == 5
        assert settings.storage.run_dir == "data/runs"
        assert settings.storage.history_weeks == 8
        assert settings.storage.cleanup_after_weeks == 12

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_settings(tmp_path / "nonexistent.yaml")

    def test_non_mapping_yaml_raises(self, tmp_path):
        p = tmp_path / "settings.yaml"
        p.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            load_settings(p)


# ---------------------------------------------------------------------------
# Competitors tests
# ---------------------------------------------------------------------------

class TestLoadCompetitors:
    def test_loads_valid_competitors(self, tmp_path):
        path = _write_yaml(tmp_path, "competitors.yaml", VALID_COMPETITORS)
        products = load_competitors(path)
        assert len(products) == 1
        p = products[0]
        assert p.competitor_name == "Chewy"
        assert p.competitor_slug == "chewy"
        assert p.canonical_name == "NexGard 10-24lbs 6-pack"
        assert p.slug == "nexgard-10-24lb-6pk"
        assert p.category == "flea_tick_oral"
        assert p.expected_price_range == (150, 200)

    def test_flattens_multiple_competitors_and_products(self, tmp_path):
        data = {
            "competitors": [
                {
                    "name": "Chewy", "slug": "chewy",
                    "products": [
                        {"canonical_name": "Product A", "slug": "prod-a",
                         "url": "https://chewy.com/a", "category": "cat1",
                         "expected_price_range": [10, 20]},
                        {"canonical_name": "Product B", "slug": "prod-b",
                         "url": "https://chewy.com/b", "category": "cat1",
                         "expected_price_range": [30, 50]},
                    ],
                },
                {
                    "name": "PetMeds", "slug": "petmeds",
                    "products": [
                        {"canonical_name": "Product A", "slug": "prod-a",
                         "url": "https://petmeds.com/a", "category": "cat1",
                         "expected_price_range": [10, 20]},
                    ],
                },
            ]
        }
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        products = load_competitors(path)
        assert len(products) == 3
        slugs = [p.competitor_slug for p in products]
        assert slugs.count("chewy") == 2
        assert slugs.count("petmeds") == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_competitors(tmp_path / "nonexistent.yaml")

    def test_missing_competitor_name_raises(self, tmp_path):
        data = {"competitors": [{"slug": "chewy", "products": []}]}
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        with pytest.raises(ValueError, match="missing required fields"):
            load_competitors(path)

    def test_missing_product_url_raises(self, tmp_path):
        data = {
            "competitors": [{
                "name": "Chewy", "slug": "chewy",
                "products": [{
                    "canonical_name": "X", "slug": "x",
                    "category": "cat", "expected_price_range": [10, 20]
                    # missing 'url'
                }]
            }]
        }
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        with pytest.raises(ValueError, match="missing required fields"):
            load_competitors(path)

    def test_bad_price_range_raises(self, tmp_path):
        data = {
            "competitors": [{
                "name": "Chewy", "slug": "chewy",
                "products": [{
                    "canonical_name": "X", "slug": "x", "url": "https://x.com",
                    "category": "cat", "expected_price_range": [200, 100]  # low > high
                }]
            }]
        }
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        with pytest.raises(ValueError):
            load_competitors(path)

    def test_price_range_must_be_two_elements(self, tmp_path):
        data = {
            "competitors": [{
                "name": "Chewy", "slug": "chewy",
                "products": [{
                    "canonical_name": "X", "slug": "x", "url": "https://x.com",
                    "category": "cat", "expected_price_range": [100]  # only one element
                }]
            }]
        }
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        with pytest.raises(ValueError, match="2-element list"):
            load_competitors(path)

    def test_defaults_applied_when_optional_fields_absent(self, tmp_path):
        data = {
            "competitors": [{
                "name": "Chewy", "slug": "chewy",
                "products": [{
                    "canonical_name": "X", "slug": "x", "url": "https://x.com",
                    "category": "cat", "expected_price_range": [10, 20]
                }]
            }]
        }
        path = _write_yaml(tmp_path, "competitors.yaml", data)
        products = load_competitors(path)
        assert products[0].rate_limit_delay_seconds == 3.0
        assert products[0].viewport == {"width": 1280, "height": 900}
