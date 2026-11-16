# Competitor Pricing Monitor

A weekly pipeline that captures competitor product pages, extracts prices with Claude, stores the history, and writes a trend analysis for the pricing team.

## Pipeline

1. **Scrape:** `scraper/` uses Playwright to screenshot each configured product page, with a per-site rate limit and a concurrency cap.
2. **Extract:** `extraction/` sends each screenshot to Claude Haiku (vision), parses the result into typed models, and checks it against the expected price range.
3. **Store:** `storage/` keeps run history in SQLite and exports CSV.
4. **Analyze:** `analysis/` sends 8 weeks of history to Claude Sonnet for a trend and risk summary.
5. **Report:** `cli.py report` prints the Markdown report. `dashboard.html` is a static mockup of the dashboard view, filled with illustrative data.

Configuration lives in `config/competitors.yaml` (sites, products, URLs, expected ranges) and `config/settings.yaml` (models, concurrency, retention). The own-storefront URLs in the config are placeholders.

## Setup

```bash
cd pricing_monitor
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
export ANTHROPIC_API_KEY=...                        # or put it in a .env file
```

## Usage

```bash
python __main__.py run                 # full run for today
python __main__.py run --date 2026-05-04
python __main__.py report              # Markdown report for the latest run
python __main__.py export -o out.csv   # CSV export
```

## Tests

```bash
pytest tests/unit tests/integration
```

195 tests. External calls (browser and Anthropic API) are mocked, so no API key or network access is needed.

`.github/workflows/pricing_monitor.yml` shows how the weekly scheduled run is set up when this folder is a standalone repo. The tests themselves run in CI from the repo root.
