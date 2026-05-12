# Multi-Sport Adapter Overhaul — 2026-05-12

## Summary
Comprehensive adapter improvements across basketball, hockey, tennis, volleyball, and football.

## Basketball (completed)
- **Basketball-Reference adapter**: Deep box score parsing (12 stat keys), team season averages, schedule with deep links, `get_deep_links()` for discovery
- **API-Basketball**: Fixed hardcoded season "2024-2025" → dynamic computation (`now.month >= 10`), added 5 stat keys (offensive_rebounds, defensive_rebounds, fast_break_points, points_in_paint, fouls), sanitized cache keys
- **nba-api client**: New `scripts/api_clients/nba_api_client.py` — free NBA stats via nba_api package (1 req/sec)
- **Fallback chain**: ESPN → nba-api → API-Basketball → SerpAPI
- **BallDontLie**: Deprecated (`_HOST_BROKEN = True`), removed from CLIENT_REGISTRY
- **Tests**: 11 unit (api_basketball) + 11 unit (basketball_reference) + 7 live tests

## Hockey (completed)
- **Hockey-Reference**: Box score parsing — shots, PIM, PP, hits, blocks, faceoffs, period scores, goalie stats
- **NaturalStatTrick adapter** (NEW): Team season stats (Corsi, Fenwick, xG, HDCF) + game logs
- **DailyFaceoff adapter** (NEW): Starting goalie confirmations with `__NEXT_DATA__` JSON parsing + HTML fallback
- **Covers adapter**: NHL-specific extraction — goalie names, PP/PK%, records
- **Hockey scanner**: Config-driven URLs from `scan_urls.json` (was 11 hardcoded → 33+ from config)
- **Tests**: 11 unit tests covering all 3 hockey adapters

## Tennis (completed + verified 2026-05-12)
- **TennisExplorer**: Complete rewrite with paired-row parser (2 rows per match). Bookmaker link filtering (bet365/1xBet/Unibet/bwin regex), seed stripping, case-insensitive skip set, date/time label filtering. **Live tested: 302 matches from /matches/, 94% match_url coverage.**
- **ATP Tour adapter** (NEW): Scores page, rankings page, draws page parsing with embedded JSON support. Requires Playwright (403 with requests).
- **TennisAbstract**: Fixed table detection (now targets `table#reportable` instead of largest table by row count). Header-based column mapping with `_col()` helper. **Live tested: 518 ATP (Sinner Elo=2331.1) + 542 WTA (Sabalenka Elo=2254.2).**
- **fetch_tennis_elo.py** (NEW): Fetches/caches ATP+WTA Elo ratings to `stats_cache/tennis_elo/`. AGENT_SUMMARY output.
- **enrich_tennis_stats.py**: H2H enrichment via ESPN athlete-vs-athlete API + `--verbose` + AGENT_SUMMARY. **Live tested: 2560 matches indexed from 640 players.**
- **compute_safety_scores.py**: `lookup_tennis_elo()` fixed (correct glob `*_elo.json`, unwrap dict `data.get("players", [])`, correct key `entry.get("home")`). `_fuzzy_player_match()` fixed (last name + first initial matching). `has_elo` adds +1 to data quality score.
- **normalize_adapter_output**: Returns `None` for `_elo_only`/`_ranking_only` records. **All callers fixed to handle None** (scan_events.py, base_scanner.py, normalize_batch).
- **Tennis scanner**: `required_stat_keys` aligned with ESPN output (`games_won`, `sets_won`, `total_games`). Added `desired_stat_keys` and `validate_event()`.
- **Deep links**: TennisExplorer patterns registered (`/match-detail/`, `/head-to-head/`, tournament pages). **All 6 test patterns pass.**

### Bugs Found and Fixed During Verification
- C1: `lookup_tennis_elo` wrong glob (`*_summary.json` → `*_elo.json`), wrong type (expected list → unwrap dict), wrong key (`"player"` → `"home"`)
- C2: Deep link patterns required `?id=\d+` which gets stripped → removed query string requirement
- C3: TennisAbstract hardcoded column indices off-by-one → header-based column mapping
- C4: Fuzzy player match substring `in` operator matched wrong players → word-boundary matching
- C5: `_elo_only` records flowing into event pipeline → normalization filter gate + caller None handling
- C6: TennisAbstract table detection picking wrapper table instead of `#reportable` → direct ID selector

## Volleyball (completed)
- **Normalized schema**: `ENRICHED_EVENT_DEFAULTS["volleyball"]` with 12 stat keys
- **Flashscore**: Volleyball set score enrichment (sets_won_home/away, total_points)
- **Scores24**: Volleyball stat extraction (aces, blocks, kills, etc.)
- **Sofascore**: match_url emission for deep enrichment
- **ESPN volleyball**: Registered `espn-volleyball` client in CLIENT_REGISTRY
- **Volleyball scanner**: Config-driven URLs from `scan_urls.json` (was 17 → 43)
- **Base scanner**: `validate()` now checks stat coverage (warning-level)

## Football (plan only)
- Created `betting/plans/football-adapters-overhaul.plan.md` — 16 tasks across 6 phases

## Deep Link Discovery Updates
Added domain patterns for: basketball-reference.com, hockey-reference.com, naturalstattrick.com, tennisexplorer.com

## Files Created (7)
- `scripts/adapters/naturalstattrick_adapter.py`
- `scripts/adapters/dailyfaceoff_adapter.py`
- `scripts/adapters/atptour_adapter.py`
- `scripts/api_clients/nba_api_client.py` (existed before, confirmed working)
- `scripts/fetch_tennis_elo.py`
- `scripts/_live_test_basketball.py`
- `scripts/_live_test_tennis_adapters.py`

## Key Data Flow
Adapters → `normalize_adapter_output()` (filters `_elo_only`/`_ranking_only` → returns None) → scan results JSON → `fetch_api_stats.py` (fallback chains) → `build_stats_cache` → `stats_cache/{sport}/{team}.json` + DB dual-write → `deep_stats_report.py` / `compute_safety_scores.py`

### Tennis-Specific Data Flow
1. `fetch_tennis_elo.py` → `tennisabstract_adapter.parse()` → cache at `stats_cache/tennis_elo/{tour}_elo.json`
2. `enrich_tennis_stats.py` → ESPN API → L10 form + H2H data → `stats_cache/tennis/{player}.json`
3. `compute_safety_scores.py` → `lookup_tennis_elo(player, surface)` → fuzzy match → Elo data → `has_elo=True` → +1 data quality
4. TennisExplorer → `scan_events.py` → `normalize_adapter_output()` (passes fixtures, blocks Elo) → shortlist
