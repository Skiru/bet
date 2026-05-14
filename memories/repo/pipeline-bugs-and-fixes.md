# Pipeline Bugs & Fixes — Active Lessons

## Critical Bug Patterns (reference for debugging)

### 1. Phantom Fixtures (2026-05-11)
- **Cause**: Scanners scrape league pages showing MULTIPLE matchdays. Items arrive with time but NO date → assigned today's date → 11,936 phantoms.
- **Fix**: `discover_fixtures.py` skips items without explicit date. `generate_market_matrix.py` requires cross-verification against independent sources. `build_shortlist.py` has phantom detection (team in >1 unique matchup = phantom, except tennis).
- **Lesson**: Scan items are UNRELIABLE — every item must be independently confirmed by ≥1 API source before entering the matrix.

### 2. Silent Data Loss (2026-05-11)
- **Cause**: `save_analysis_results_to_db()` had `if not fixture_id: continue` with no logging → 181/200 records silently dropped per run.
- **Fix**: Added warning logs + skip counters to all persistence loops.
- **Lesson**: NEVER use bare `continue` in data persistence loops. Always log + count skips.

### 3. Absurd Statistical Lines (2026-05-11)
- **Cause**: `_round_to_half()` fallback in `normalize_stats.py` had no upper bound → corrupt L10 stats produced "Goals O/U 9.0".
- **Fix**: `_MAX_REASONABLE_LINE` dict with sport/stat-specific caps. Two guard points before and after line computation.
- **Lesson**: Always validate computed lines against sport-reasonable ranges.

### 4. Garbage Team Names (2026-05-11)
- **Cause**: Soccerway adapter scraped HTML structural elements ("Division 3", "display matches (1)"). Tennis adapter scraped bookmaker names ("1xBet vs bet365").
- **Fix**: Extended `_garbage_re` + `_bookmaker_vs_re` + min length + all-digit rejection.
- **Lesson**: Review scan_results quality regularly. New scraping sources = new garbage patterns.

### 5. Dead API Sources (2026-05-11)
- `balldontlie` (100% fail), `api-tennis` (NXDOMAIN), `thesportsdb` (97.8% fail).
- All set to `_HOST_BROKEN = True`, removed from fallback chains and CLIENT_REGISTRY.
- **Lesson**: Need source health monitoring. Disable sources above failure threshold.

### 6. Fixture Kickoff Format (2026-05-11)
- **Cause**: `discover_fixtures.py` wrote `kickoff=event_time` (just "20:00") instead of full ISO datetime.
- **Fix**: `kickoff=event_date or (f"{date}T{event_time}" if event_time else "")`.
- **Lesson**: Always validate kickoff format after ingestion.

### 7. SQL Injection (2026-05-11)
- **Cause**: f-string interpolation in SQL in `_diag_quality.py`.
- **Fix**: Parameterized queries everywhere.
- **Lesson**: NEVER use f-strings in SQL. Always `?` placeholders.

### 8. Sofascore 403 Waste (2026-05-13)
- **Cause**: Pipeline fell back to Flashscore (alphanumeric IDs), then enrichment called Sofascore with those IDs → Playwright navigated to homepage → 15s wasted × 225 events.
- **Fix**: `_is_sofascore_id()` guard (numeric-only), source-aware routing in `unified.py`.
- **Status**: Sofascore fully removed from active pipeline. Client code preserved as dormant insurance.

### 9. Browser Context Leak (2026-05-13)
- **Cause**: `fetch_odds_multi.py` Playwright sources never had `close()` called.
- **Fix**: Cleanup loop after scan — `hasattr(source, 'close') → source.close()`.

### 10. Scores24 Double-Path URLs (2026-05-13)
- **Cause**: `removeprefix("s24-")` on href external_ids produced malformed URLs.
- **Fix**: If `external_id.startswith('/')` → use directly; if `s24-` prefix → skip.

## Data Flow Verification Protocol (R18)
Before running ANY script: READ its code, understand what it READS and WRITES. TRACE the connection to the NEXT script. Verify with actual data. The #1 source of pipeline failures is data format mismatches between producer/consumer scripts.

## Key Anti-Patterns
- Bare `continue` in data persistence loops (silent data loss)
- No upper-bound validation on computed statistical lines
- Assuming scripts "just work" without reading their code
- f-strings in SQL queries
- Fire-and-forget browser contexts without cleanup
