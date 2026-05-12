# PERMANENT REP MEMORY: Stealth HTML Warmup & Adapter Cleanup

## Established 2026-05-12

### The Problem
Traditional Playwright scraping for Betclic, OddsPortal, and BetExplorer was failing due to heavy Cloudflare/Datadome protection (403 Forbidden). The old HTML adapters (`betclic_scraper.py`, `oddsportal_scraper.py`, `betclic_login.py`) were dead code, clogging the pipeline and making it fragile.

### The Solution (New Architecture)
1. **Removed Dead Code**: All old scraper adapters and login scripts have been permanently deleted from `scripts/odds_sources/`.
2. **Beast Mode Default**: The pipeline is natively "Stats-First" or "Beast Mode". We rely on API aggregators (The-Odds-API, Sofascore) for core flow.
3. **S0.1 Stealth Warm-up (`daily_odds_warmup.py`)**: 
   - Instead of scraping dynamically, we use a single warm-up script equipped with `playwright-stealth` (masking `navigator.webdriver`).
   - It rapidly fetches full, lazy-loaded DOMs from protected bookmakers (Betclic) in seconds.
   - HTML files are dumped to `betting/data/html_cache/` (e.g., `2026-05-12_betclic_football.html`).
   - Downstream components can now perform fast, local Regex/BeautifulSoup parsing on these files without risking live API blocks.

### Rule for Future Scrapers
**DO NOT write live-scraping Playwright integrations into the main pipeline.** Any new protected source should be added to the `daily_odds_warmup.py` array to dump its HTML locally first. Live pipeline scripts must ONLY analyze the local `.html` cache!