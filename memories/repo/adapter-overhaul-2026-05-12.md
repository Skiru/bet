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

## Hockey (completed + MoneyPuck verified 2026-05-12)
- **Hockey-Reference**: Box score parsing — shots, PIM, PP, hits, blocks, faceoffs, period scores, goalie stats
- **NaturalStatTrick adapter**: Team season stats (Corsi, Fenwick, xG, HDCF) + game logs. **⚠️ SOURCE BLOCKED by Cloudflare "Under Attack" mode — 403 on ALL methods. Adapter code works but source unreachable.**
- **MoneyPuck adapter** (NEW — **PRIMARY** NHL advanced stats): Free CSV API, no auth, no Cloudflare. 32 NHL teams, 40 stat keys (37 raw + 3 derived: shooting%, save%, PDO). **Live verified**: 99KB CSV → 160 rows cached (12h TTL) → fuzzy team name matching works (Tampa Bay, Bruins, VGK, etc.). Integrated in `deep_stats_report.py` enrichment for hockey candidates.
- **DailyFaceoff adapter** (NEW): Starting goalie confirmations with `__NEXT_DATA__` JSON parsing + HTML fallback
- **Covers adapter**: NHL-specific extraction — goalie names, PP/PK%, records
- **Hockey scanner**: Config-driven URLs from `scan_urls.json` (was 11 hardcoded → 33+ from config)
- **Tests**: 20 unit tests covering all 4 hockey adapters (hockey-reference, naturalstattrick, dailyfaceoff, moneypuck)

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

## Football (completed + verified 2026-05-12)
All 8 football adapters enhanced with verbose logging, deep links, dedup, sport/source_type fields:
- **BetExplorer**: Sport auto-detection from URL, `get_deep_links()`, verbose logging, dedup. **Live: 235 matches via HTTP.**
- **Sofascore**: API-first with REST endpoints, `get_deep_links()` for per-event stats. **Live: 80 matches, 160 deep links.**
- **Forebet**: `get_deep_links()` from tnmscn links, verbose logging. **Live: 44 matches + 44 deep links.**
- **Flashscore**: Raw fallback (SPA). **Live: 45 matches via HTTP (raw).**
- **Soccerway**: Soccerway-specific selectors (team-a/team-b/score-time), absolute match_url, raw fallback enriches sport/source_type, `get_deep_links()`. **Live: 38 matches via HTTP (raw fallback).**
- **WhoScored**: JSON data-stats parsing, explicit away=None stats, `get_deep_links()` from Matches/ID/Live/ + div.Match data-id. **Needs Playwright (HTTP 403).**
- **OddsPortal**: Fixed deep link pattern (actual match URLs, not /h2h/), verbose logging, `get_deep_links()`. **Needs Playwright (SPA, 0 matches via HTTP).**
- **SoccerStats**: Safe float parsing (try/except), removed duplicate source/url fields, `get_deep_links()` for results/teams/homeaway. **Needs correct URL or Playwright.**
- **TotalCorner**: match_url extraction, `get_deep_links()` for /match/ /corner/ sub-pages. **Needs Playwright (JS).**
- **raw_adapter**: Auto-detects sport from URL and source_type from domain — fallback results now have pipeline traceability.

### Football Live Test Results (HTTP only)
| Adapter | Matches | Deep Links | Status |
|---------|---------|------------|--------|
| BetExplorer | 235 | 0 | ✅ PASS |
| Sofascore API | 80 | 160 | ✅ PASS |
| Forebet | 44 | 44 | ✅ PASS |
| Flashscore | 45 | 0 | ✅ PASS (raw) |
| Soccerway | 38 | 0 | ✅ PASS (raw fallback) |
| OddsPortal | 0 | 0 | ✅ Expected (SPA) |
| TotalCorner | 0 | 0 | ✅ Expected (JS) |
| WhoScored | 0 | 0 | ❌ HTTP 403 (Playwright needed) |
| SoccerStats | 0 | 0 | ❌ HTTP 404 (wrong URL/Playwright) |

## Deep Link Discovery Updates
Added domain patterns for: basketball-reference.com, hockey-reference.com, naturalstattrick.com, tennisexplorer.com, whoscored.com, totalcorner.com, forebet.com, soccerstats.com, covers.com.
Fixed: query string preservation (was stripping `?id=` params), relaxed TennisExplorer `/match-detail/` pattern (no longer requires `?id=\d+`).

## Files Created
- `scripts/adapters/naturalstattrick_adapter.py`
- `scripts/adapters/dailyfaceoff_adapter.py`
- `scripts/adapters/atptour_adapter.py`
- `scripts/adapters/moneypuck_adapter.py` (NEW — NHL advanced stats from CSV)
- `scripts/api_clients/moneypuck_client.py` (NEW — MoneyPuck CSV client, 37 stats/team)
- `scripts/api_clients/nba_api_client.py`
- `scripts/fetch_tennis_elo.py`
- `scripts/_live_test_basketball.py`
- `scripts/_live_test_tennis_adapters.py`
- `scripts/_live_test_football_adapters.py` (NEW)
- `scripts/_verify_db_pipeline.py` (NEW — DB save verification)

## Files Modified (football-specific)
- `scripts/adapters/betexplorer_adapter.py` — sport detection, logging, get_deep_links()
- `scripts/adapters/forebet_adapter.py` — logging, get_deep_links()
- `scripts/adapters/oddsportal_adapter.py` — logging, fixed deep link pattern, get_deep_links()
- `scripts/adapters/sofascore_adapter.py` — logging, get_deep_links() via API
- `scripts/adapters/soccerway_adapter.py` — Soccerway selectors, absolute match_url, raw fallback enrichment, get_deep_links()
- `scripts/adapters/soccerstats_adapter.py` — logging, safe float parsing, dedup, get_deep_links()
- `scripts/adapters/totalcorner_adapter.py` — logging, match_url extraction, get_deep_links()
- `scripts/adapters/whoscored_adapter.py` — logging, JSON data-stats parsing, explicit away stats, get_deep_links()
- `scripts/adapters/raw_adapter.py` — sport/source_type auto-detection from URL/domain
- `scripts/deep_link_discovery.py` — 5 new domain patterns, query string preservation fix
- `scripts/adapters/__init__.py` — _elo_only/ranking_only filtering in normalize_adapter_output(), normalize_batch() None handling
- `scripts/scan_events.py` — None handling for normalize_adapter_output()
- `scripts/scanners/base_scanner.py` — None handling for normalize_adapter_output()

## Key Data Flow
Adapters → `normalize_adapter_output()` → scan results JSON → `fetch_api_stats.py` (fallback chains) → `build_stats_cache` → `stats_cache/{sport}/{team}.json` + DB dual-write → `deep_stats_report.py` / `compute_safety_scores.py`
