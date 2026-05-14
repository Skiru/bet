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

## ⛔ CRITICAL: 2026-05-13 Post-Mortem — 5 Systemic Bugs (ALL FIXED in commit b31a3ca)

**Every agent analyzing picks MUST know these patterns — they caused a full coupon loss (1W/3L, -2.0 PLN).**

### Bug #1: CONTEXT BLINDNESS — No Opponent Quality Adjustment
- **What happened**: Lens corners avg 7.7 in L10 → pipeline recommended Over 5.5 (safety 0.63). But those 7.7 corners were earned against AVERAGE Ligue 1 opponents. Against PSG (70% possession, total domination → 0-2 loss), Lens couldn't generate attacks.
- **Root cause**: Safety score treated "corners vs relegation fodder" identically to "corners vs PSG"
- **Fix**: `gate_checker.py` ZT#23 — flags stat markets (corners/fouls/shots) when opponent is top-5 in standings. Queries DB standings.
- **Rule for ALL agents**: When evaluating stat markets, ALWAYS check opponent strength. Raw L10 averages are MEANINGLESS without opponent context.

### Bug #2: ONE-SIDED DATA — Missing Opponent Accepted
- **What happened**: DC United vs Chicago Fire — DC United had `has_data=False` (no form data at all). Pipeline still produced safety=0.56 recommendation using only Chicago Fire's stats.
- **Root cause**: `one_sided` penalty was only 0.70 multiplier (allowed 0.56 through)
- **Fix**: `compute_safety_scores.py` — one_sided safety HARD CAPPED at **0.40** (cannot exceed regardless of hit rate)
- **Rule for ALL agents**: If EITHER team has no data, the pick is LOW CONFIDENCE. Never trust one-sided analysis.

### Bug #3: DUPLICATE FIXTURES — Contradictory Recommendations
- **What happened**: "RC Lens vs Paris Saint Germain", "Lens vs Paris Saint-Germain", "Lens vs PSG" appeared as 3 separate analysis_results. DC United vs Chicago Fire appeared 2x with OPPOSITE directions (Under 3.5 vs Over 5.5).
- **Root cause**: No deduplication of fixtures by normalized team names before analysis
- **Fix**: `deep_stats_report.py` — dedups fixtures by normalized names (accent-stripped, FC/SC/RC removed, substring match) BEFORE analysis loop
- **Rule for ALL agents**: If you see the same match multiple times with different recommendations, it's a BUG. Report it.

### Bug #4: SMALL SAMPLE BIAS — Early Season Trap
- **What happened**: WNBA Toronto Tempo had only 7 games in L10 (early season). Pipeline computed safety=0.60 from 7 data points. Toronto scored 86 vs predicted avg 106 (19% miss).
- **Root cause**: No sample size check — 7 games treated same as 10 games
- **Fix**: `compute_safety_scores.py` Pattern I — safety CAPPED at **0.50** when L10 has fewer than 8 games
- **Rule for ALL agents**: Early-season events (WNBA, new leagues, start of season) have UNRELIABLE stats. Flag them as LOW CONFIDENCE.

### Bug #5: ODDS vs SAFETY DISAGREEMENT — Market Knows Something
- **What happened**: Lens Over 5.5 corners: pipeline safety=0.63 (63% confident) but Betclic odds @2.67 = 37.5% implied probability. A **25.5 percentage point gap** between model and market went UNFLAGGED.
- **Root cause**: No automated check comparing model confidence vs market pricing
- **Fix**: `gate_checker.py` Gate #19 `_check_odds_safety_gap()` — flags when gap exceeds 15 percentage points. Labels as OVERCONFIDENT or UNDERCONFIDENT.
- **Rule for ALL agents**: When your model says 63% but the market says 37% → THE MARKET IS PROBABLY RIGHT. This gap means your model is missing something (opponent quality, context, news).

### Pattern Tags (stored in decision_outcomes DB table for automated detection)
```
opponent_quality_mismatch — stat avg earned vs weak opponents, now facing elite
missing_opponent_data — one-sided analysis, only 1 team has form data  
small_sample_bias — L10 has <8 games (early season, new team, short tournament)
duplicate_fixture_conflict — same match appears 2-3x with contradictory recs
odds_vs_safety_disagreement — >15pt gap between model safety and market implied prob
```

---

## Data Flow Verification Protocol (R18)
Before running ANY script: READ its code, understand what it READS and WRITES. TRACE the connection to the NEXT script. Verify with actual data. The #1 source of pipeline failures is data format mismatches between producer/consumer scripts.

## Key Anti-Patterns
- Bare `continue` in data persistence loops (silent data loss)
- No upper-bound validation on computed statistical lines
- Assuming scripts "just work" without reading their code
- f-strings in SQL queries
- Fire-and-forget browser contexts without cleanup
- **Trusting raw L10 averages without opponent context (Bug #1)**
- **Accepting one-sided analysis as reliable (Bug #2)**
- **Not checking for duplicate fixture names (Bug #3)**
- **Treating <8 game samples as reliable (Bug #4)**
- **Ignoring large model-vs-market probability gaps (Bug #5)**
