# Stealth Playwright Alignment — 2026-05-13

## What was done
Aligned `playwright_stealth` v2 library across ALL source-fetching scripts.
Previously only `sofascore.py` and `data_enrichment_agent.py` had proper stealth.

## Files changed (6)
1. `scripts/stealth_fetcher.py` — async shared utility
2. `scripts/daily_odds_warmup.py` — S0.1 Betclic HTML cache warmup  
3. `src/bet/api_clients/flashscore.py` — added full `_request_playwright()` fallback
4. `scripts/settle_on_finish.py` — Flashscore batch result fetcher
5. `scripts/fetch_betclic_bets.py` — Betclic /my-bets scraper
6. `scripts/verify_betclic_odds.py` — Betclic odds verification

## Stealth pattern (canonical)
```python
# SYNC
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
browser = p.chromium.launch(headless=True, args=[
    '--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox'
])
context = browser.new_context(user_agent="...", viewport={"width": 1920, "height": 1080})
page = context.new_page()
Stealth().apply_stealth_sync(page)  # BEFORE any page.goto()

# ASYNC
await Stealth().apply_stealth_async(page)
```

## Bugs found and fixed in review pass
1. **flashscore.py `_request_playwright()` returned full HTML** — callers expect raw text feed (¬/÷ delimited). Fixed: use `page.inner_text("body")`.
2. **flashscore.py double APIError wrapping** — `except Exception` caught and re-wrapped `APIError`, losing `status_code`. Fixed: `except APIError: raise` before generic handler.
3. **flashscore.py fell back to Playwright on ALL RequestExceptions** (DNS, timeout) — wasteful. Fixed: only 403/429 like sofascore.py.
4. **stealth_fetcher.py missing Cloudflare JS challenge wait** — "Just a moment" page returned None immediately. Fixed: added 5s wait + retry.
5. **3 files had `from playwright_stealth import Stealth` inside `with sync_playwright():`** — if import fails, playwright context leaks. Fixed: moved to `try/except ImportError` before the `with` block, with `Stealth = None` fallback.

## Files NOT changed (already good or N/A)
- `sofascore.py` — reference pattern ✅
- `data_enrichment_agent.py` — reference pattern ✅  
- `fetch_odds_api.py`, `fetch_weather.py`, `serpapi_client.py`, `odds_api_io.py` — API key auth, won't 403
- `tipster_aggregator.py` — plain requests, tipster sites rarely 403
