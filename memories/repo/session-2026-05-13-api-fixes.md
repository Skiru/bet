# Session 2026-05-13: API Client Fixes + Full Pipeline Re-run

## Problem
- Previous pipeline run for 2026-05-13 was catastrophically incomplete: 73% of events (320/441) had NO analysis
- Both `deep_stats_report.py` (exit 143) and `data_enrichment_agent.py` (exit 143) were killed before completion
- Dashboard showed "brak analizy" for hundreds of events

## Root Causes Found
1. **Sofascore JSON API**: Returns 403 even with stealth Playwright (server-side bot detection). HTML website works with stealth (621K bytes) but URL slugification is broken — sites need hash IDs (e.g., `/team/manchester-city/ltxGwk7j/`) which we don't have
2. **playwright-stealth v2 import**: Correct API is `from playwright_stealth import Stealth` then `Stealth().apply_stealth_sync(page)` — NOT `stealth(page)` or `stealth_sync(page)`
3. **H2H stealth timeout**: `extract_h2h_stats()` in `deep_stats_report.py` didn't check `NO_ENRICH` env var, causing 30-second stealth timeouts per event during H2H lookups
4. **Flashscore client**: Complete stub — all methods return empty lists with warnings

## Fixes Applied

### scripts/data_enrichment_agent.py
- `fetch()` function: Added stealth Playwright fallback for 403/429 responses
- New `_fetch_stealth()` function using `Stealth().apply_stealth_sync(page)` with Chromium args

### scripts/deep_stats_report.py
- `extract_h2h_stats()` line 489: Added `os.environ.get("NO_ENRICH")` check before online H2H lookup

### src/bet/api_clients/sofascore.py
- `_request_playwright()`: Updated to use `Stealth().apply_stealth_sync(page)` with proper Chromium stealth args
- Added DataDome detection alongside Cloudflare

### src/bet/api_clients/flashscore.py
- Added warning logs to all stub methods

## Pipeline Results (After Fix)
- **Deep Stats**: 441 candidates processed, 213 with data (was 121 — +76%), 0 errors
- **Gate Checker**: 434 events → 141 approved, 227 extended, 66 rejected
- **Coupons**: 50 singles (was 26), 112+ entries in full matrix, 4 sports

## API Client Status
| Client | Status | Coverage |
|--------|--------|----------|
| ESPN | WORKING, free, no key | Football, basketball, hockey, tennis, volleyball |
| Sofascore | JSON=403, HTML stealth=works but URLs broken | Limited by slug generation |
| Flashscore | STUB (all methods return []) | None |
| The-Odds-API | Working, 500/month free | Odds only |

## Key Lesson
- ESPN API is the reliable workhorse — free, unlimited, no blocks
- Sofascore JSON API is too well protected for any stealth approach (server-side)
- The massive stats_cache (9,600+ files) is the real data source for analysis
- `--from-db --no-enrich` flags on deep_stats = fast re-run using cached data

## Future Improvements
- Wire ESPN API into `data_enrichment_agent.py` (currently only used by `scan_events.py` and `seed_espn_data.py`)
- Fix URL slugification for Flashscore/Sofascore HTML (needs team ID mapping)
- Consider building a team_id → site_slug mapping table in DB
