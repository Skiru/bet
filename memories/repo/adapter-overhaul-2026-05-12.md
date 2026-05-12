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

## Tennis (completed)
- **TennisExplorer**: H2H page parsing, surface/country extraction, match_url deep links, score extraction, source_type field
- **ATP Tour adapter** (NEW): Scores page, rankings page, draws page parsing with embedded JSON support
- **TennisAbstract**: `_elo_only` flag, logging, used by `fetch_tennis_elo.py` for safety score Elo data
- **fetch_tennis_elo.py** (NEW): Fetches/caches ATP+WTA Elo ratings to `stats_cache/tennis_elo/`
- **enrich_tennis_stats.py**: H2H enrichment via ESPN Stats API + H2H cache

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
Adapters → `normalize_adapter_output()` → scan results JSON → `fetch_api_stats.py` (fallback chains) → `build_stats_cache` → `stats_cache/{sport}/{team}.json` + DB dual-write → `deep_stats_report.py` / `compute_safety_scores.py`
