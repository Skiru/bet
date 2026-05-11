# Pipeline Lessons Learned

## 2026-05-11: Four Critical Bugs Found

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
