# Pipeline Lessons Learned

## 2026-05-11 (night): Phantom Fixture Bug — CRITICAL

### Root Cause: Dateless Scan Items Assigned Today's Date
- **Problem**: Playwright scanners scrape league schedule pages showing MULTIPLE matchdays. Items arrive with time (e.g., "21:00") but NO date.
- `discover_fixtures.py` was including items with just a time field, creating fixtures like `2026-05-11T21:00` by prepending today's date
- `generate_market_matrix.py` was accepting all scan items with time/odds without any date verification
- **Result**: 11,936 of 12,162 scan items had no date → all assigned to today → Europa League Final (May 20), future matchdays, etc. appeared as today's fixtures
- **Impact**: Market matrix had 4,664 events instead of ~150. Coupons contained phantom matches.

### Fixes Applied (4 scripts + 1 new utility)
1. **`discover_fixtures.py`**: `_load_scan_summary()` now SKIPS items without explicit date field. `_persist_fixtures_to_db()` validates kickoff starts with "20" before persisting.
2. **`generate_market_matrix.py`**: SCAN EXPANSION requires cross-verification against independent sources (odds_lookup, multi_odds, analysis_pool, fixture_keys). Fuzzy matching tightened to require BOTH teams match with min 6-char length.
3. **`db_data_loader.py`**: Phantom detection now flags ALL teams appearing in >2 scan fixtures (removed "is_in_api" exemption that let phantoms pass).
4. **`api_clients/api_tennis.py`**: Disabled — `v1.tennis.api-sports.io` returns NXDOMAIN (DNS doesn't resolve). `_HOST_BROKEN = True` makes it fail fast.
5. **`scripts/clean_phantom_fixtures.py`**: New utility to clean phantom fixtures from DB with FK cascade handling.

### DB Cleanup
- Deleted 25,184 corrupted fixtures (5,336 playwright-scan phantoms + 19,848 with bare-time kickoff)
- Final DB: 10,616 fixtures (from 30,464)

### Verification
- May 11 matrix: 4,664 → 141 events (correct)
- May 12 matrix: 0 events (expected — APIs haven't been called for tomorrow yet)
- Remaining edge case: 1 team (Gil Vicente) with 3 matches from DB (below filter threshold of >2 for scan fixtures, partially from API)

### Key Lesson: CROSS-VERIFICATION IS MANDATORY
- Scan items are UNRELIABLE — they contain fixtures from multiple matchdays/rounds
- Every scan item must be independently confirmed by at least one API source before entering the matrix
- The pipeline went from "trust all scan items" to "verify or reject"

## 2026-05-11 (earlier): Four Critical Bugs Found

### Bug Chain: Fixture Kickoff → S3 DB Write → League Profiles
- **Root cause**: `discover_fixtures.py` wrote `kickoff=event_time` (just `"20:00"`) instead of `"{date}T{event_time}"` when `event_date` was empty
- **Impact**: `_resolve_fixture_id()` extracted `"20:00"` as date → no match → `save_analysis_results_to_db()` silently skipped 181/200 records → only 19 saved
- **League profiles**: Query joins `fixtures → match_stats` — broken fixtures broke the join → 0 profiles built
- **Fix**: `discover_fixtures.py` line 140: `kickoff=event_date or (f"{date}T{event_time}" if event_time else "")`
- **Fix**: `db_data_loader.py`: Added `_create_minimal_fixture()` fallback + warning logs instead of silent `continue`

### Dead API Sources
- `balldontlie` (100% fail), `api-tennis` (100% fail), `thesportsdb` (97.8% fail) wasted time in fallback chains
- Disabled in `fetch_api_stats.py` FALLBACK_CHAINS
- **Lesson**: Need automated source health monitoring that disables sources above a failure threshold

### Silent Data Loss Pattern
- `save_analysis_results_to_db()` and `save_gate_results_to_db()` had `if not fixture_id: continue` — no log, no counter
- 181 records silently dropped per run
- **Lesson**: NEVER use bare `continue` in data persistence loops. Always log + count skips.

## Methodology Gaps Identified (2026-05-11)
1. No fixture kickoff format validation after ingestion
2. No source health auto-disable mechanism
3. No DB write count verification (input vs saved)
4. Missing `pipeline-lessons-learned.md` (this file!) was referenced in STEP 0 but didn't exist

## 2026-05-11: SPA Content-Ready Selectors + Adapter Enrichment

### Problem: 3 SPA domains returning 0 events
- **oddsportal.com**, **scores24.live**, **atptour.com** — all React/JS SPAs
- `fetch_with_playwright.py` had `wait_after_load=500ms` — too short for SPA hydration
- Adapters couldn't parse pre-hydration HTML shells

### Solution: Content-Ready Selector Infrastructure
- `site_selectors.json` → new `_content_ready` section with per-domain CSS selectors, timeouts, settle times
- `fetch_with_playwright.py` → `load_content_ready_config()` + `page.wait_for_selector()` after cookie consent
- Non-SPA domains unaffected (still use original 500ms wait)

### OddsPortal Adapter Rewrite
- React DOM has `.participant-name` elements (paired home/away) + `.default-odds-bg-bgcolor` odds elements
- New Strategy 1: parse participant pairs, walk up DOM to find odds container
- Result: **0 → 51 events** with structured 3-way odds (home_win/draw/away_win)
- Match URLs via `/h2h/` links (only 1 found in listing page — detail pages have more)

### Scores24 Content Selectors
- Uses styled-components with hashed class names (e.g., `sc-mhmn9c`)
- Selector: `.link[class*='sc-mhmn9c']` — detects rendered match links
- Fetch time dropped from 29s (fallback wait) to 5.8s (selector-based)

### ATP Tour: Cloudflare Blocked
- Returns Cloudflare challenge page (`loading-verifying`, `ray-id`)
- Not fixable via CSS selectors — needs Cloudflare bypass or alternative data source

### Key Selectors Reference
| Domain | Content Selector | Timeout | Settle |
|---|---|---|---|
| oddsportal.com | `.participant-name` | 8000ms | 3000ms |
| scores24.live | `.link[class*='sc-mhmn9c']` | 8000ms | 3000ms |
| atptour.com | BLOCKED by Cloudflare | — | — |

### Adapter Audit Results (27 adapters tested)
- 18 working with events, 6 no data available, 3 SPA (2 now fixed), 0 errors
- Top producers: flashscore (285), betexplorer (631), forebet (68), betclic (59)
- OddsPortal now: 51 events with odds (was 0)

### ingest_scan_stats.py Bug Fix
- `_extract_form_matches()` crashed on plain string form entries (`["W", "W", "L"]`)
- Added `isinstance(entry, str)` guard before calling `.get("scores")`
- Test added: `test_ingest_deep_parse_none_safe` with string form data
