# Sofascore Source-Aware Routing Fix — 2026-05-13

## Problem
When Sofascore HTTP API returns 403 (Cloudflare WAF), pipeline falls back to Flashscore which provides **alphanumeric IDs** (e.g. `QckUTQbD`). Enrichment then called `client.sofascore.*` with these IDs causing:
- Playwright regex `r"event/(\d+)/"` failed on non-numeric → navigated to homepage
- ~15s wasted per event × 225 events = ~1 hour of dead Playwright sessions
- Circuit breaker never tripped (increment was missing)

## Fix (3 files)

### `src/bet/api_clients/sofascore.py`
- `_is_sofascore_id(event_id)` — static method, `re.fullmatch(r"\d+", str(id))`
- All 8 event methods guarded: non-numeric → instant empty return, no HTTP/Playwright
- `_request_playwright()` raises `APIError` instead of navigating to homepage when no valid target
- Circuit breaker fixed: increments `_stealth_failures` on Playwright miss, opens circuit at threshold

### `src/bet/api_clients/unified.py`
- `get_fixture_stats(event_id, source=None)` — skips Sofascore for non-numeric IDs
- `get_deep_data(event_id, source=None)` — consolidated routing:
  - Flashscore path: `get_match_preview()` (form + H2H in one call) + `get_fixture_stats()`
  - Sofascore path: individual endpoints (stats, form, H2H, odds)
  - Routes by: explicit `source` param OR `_is_sofascore_id()` check

### `scripts/scan_events.py`
- `fetch_deep_data()` simplified to use `client.get_deep_data(event_id, source)`
- Passes `ev.get("_source")` through `_enrich_single_event()`
- Singleton `UnifiedAPIClient` with thread-safe double-checked locking (fixes Playwright asyncio loop conflict when reused across ThreadPoolExecutor workers)

## Key Architecture Decision
- Fixtures carry `_source` field ("sofascore" or "flashscore") from scan phase
- Enrichment routes to matching client based on source + ID format
- Sofascore numeric IDs → Sofascore endpoints; Flashscore alphanumeric → Flashscore DOM scraping
- Flashscore `get_match_preview()` returns form + H2H in single page load (efficient)

## Test Results
- 149 existing tests pass, 5/5 enrichment events succeeded
- Zero Sofascore 403 waste after fix
